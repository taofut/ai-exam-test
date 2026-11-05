"""T1 single-material issue and whole-record return, each in one transaction."""
from sqlalchemy import update

from materialops.errors import AppError
from materialops.models import Inventory, MaterialIssue
from materialops.services.access import check_warehouse
from materialops.services.clock import now
from materialops.services.ledger import (
    begin_write,
    next_no,
    record_audit,
    record_movement,
)
from materialops.services.queries import get_issue, inventory_json
from materialops.services.scaffold_helpers import cas_stock_delta, run_atomic


def _conflict():
    return AppError("VERSION_CONFLICT", "库存或单据已变化，请刷新后重新提交。")


def issue_material(database, fallback, user, inventory_id, quantity, version, reason):
    def callback(session):
        begin_write(session)
        inventory = session.get(Inventory, inventory_id)
        if inventory is None:
            raise AppError("INVENTORY_NOT_FOUND", "库存不存在。")
        check_warehouse(session, user, inventory.warehouse_id)
        if inventory.version != version:
            raise _conflict()
        before = inventory.on_hand
        if before < quantity:
            raise AppError("STOCK_INSUFFICIENT", "可用库存不足。")
        if not cas_stock_delta(session, inventory_id=inventory.id, expected_version=version, delta=-quantity):
            raise _conflict()
        at = now(session, fallback)
        issue = MaterialIssue(issue_no=next_no("ISS"), inventory_id=inventory.id, quantity=quantity,
                              issued_by_id=user.id, reason_text=reason, issued_at=at, version=0)
        session.add(issue)
        session.flush()
        record_movement(session, inventory_id=inventory.id, item_id=inventory.item_id,
                        movement_type="ISSUE", business_no=issue.issue_no, quantity=quantity,
                        before=before, after=before - quantity, actor_id=user.id, occurred_at=at)
        record_audit(session, actor_id=user.id, action="MATERIAL_ISSUE",
                     parameters={"inventoryId": inventory.id, "quantity": quantity, "issueNo": issue.issue_no},
                     before_state={"onHand": before, "version": version},
                     after_state={"onHand": before - quantity, "version": version + 1}, occurred_at=at)
        return issue.id

    issue_id = run_atomic(database.sessions, callback)
    with database.sessions() as session:
        return {"issue": get_issue(session, user, issue_id),
                "inventory": inventory_json(session, session.get(Inventory, inventory_id), user)}


def return_material(database, fallback, user, issue_id, issue_version, inventory_version):
    with database.sessions() as session:
        record = get_issue(session, user, issue_id)
        if record["issueOrderId"] is not None:
            raise AppError("KIT_RETURN_REQUIRED", "套料子明细须随父单整单退回。")
        if record["returnedAt"]:
            raise AppError("ISSUE_ALREADY_RETURNED", "该领用记录已整单退回。")
        inventory_id, quantity = record["inventoryId"], record["quantity"]

    def callback(session):
        begin_write(session)
        at = now(session, fallback)
        updated = session.execute(update(MaterialIssue).where(
            MaterialIssue.id == issue_id, MaterialIssue.version == issue_version,
            MaterialIssue.returned_at.is_(None)).values(returned_at=at, version=MaterialIssue.version + 1))
        if updated.rowcount != 1:
            raise _conflict()
        inventory = session.get(Inventory, inventory_id)
        if inventory is None:
            raise AppError("INVENTORY_NOT_FOUND", "库存不存在。")
        before = inventory.on_hand
        if not cas_stock_delta(session, inventory_id=inventory_id,
                               expected_version=inventory_version, delta=quantity):
            raise _conflict()
        record_movement(session, inventory_id=inventory_id, item_id=inventory.item_id,
                        movement_type="RETURN", business_no=record["issueNo"], quantity=quantity,
                        before=before, after=before + quantity, actor_id=user.id, occurred_at=at)
        record_audit(session, actor_id=user.id, action="MATERIAL_RETURN",
                     parameters={"issueId": issue_id, "issueNo": record["issueNo"]},
                     before_state={"onHand": before, "version": inventory_version},
                     after_state={"onHand": before + quantity, "version": inventory_version + 1},
                     occurred_at=at)

    run_atomic(database.sessions, callback)
    with database.sessions() as session:
        return {"issue": get_issue(session, user, issue_id),
                "inventory": inventory_json(session, session.get(Inventory, inventory_id), user)}
