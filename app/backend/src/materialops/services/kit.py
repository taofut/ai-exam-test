"""T1 same-warehouse kit issue and whole-kit return as single transactions."""
from sqlalchemy import select, update

from materialops.errors import AppError
from materialops.models import Inventory, MaterialIssue, MaterialIssueOrder
from materialops.services.access import check_warehouse, warehouse_scope
from materialops.services.clock import now
from materialops.services.ledger import (
    MANAGERS,
    STATUS_ISSUED,
    STATUS_RETURNED,
    begin_write,
    line_json,
    next_no,
    order_json,
    record_audit,
    record_movement,
)
from materialops.services.queries import inventory_json
from materialops.services.scaffold_helpers import cas_stock_delta, run_atomic

MIN_LINES, MAX_LINES = 2, 5


def _invalid(message):
    return AppError("KIT_LINES_INVALID", message)


def _load_lines(session, order_id):
    return session.scalars(select(MaterialIssue).where(MaterialIssue.issue_order_id == order_id)
                           .order_by(MaterialIssue.id)).all()


def _check_lines(session, user, warehouse_id, lines):
    """Authorize the warehouse and every requested line before any version/balance check."""
    check_warehouse(session, user, warehouse_id)
    inventory_ids = [line["inventoryId"] for line in lines]
    if len(set(inventory_ids)) != len(inventory_ids):
        raise _invalid("同一物资不能重复列入套料。")
    rows = {row.id: row for row in session.scalars(
        select(Inventory).where(Inventory.id.in_(inventory_ids))).all()}
    items = set()
    for inventory_id in inventory_ids:
        inventory = rows.get(inventory_id)
        if inventory is None or inventory.warehouse_id != warehouse_id:
            raise _invalid("所选库存须属于同一仓库且真实存在。")
        if inventory.item_id in items:
            raise _invalid("同一物资不能重复列入套料。")
        items.add(inventory.item_id)
    return rows


def create_kit(database, fallback, user, warehouse_id, reason, lines):
    if not MIN_LINES <= len(lines) <= MAX_LINES:
        raise _invalid("同仓维修套料须为 2～5 种不同物资。")
    with database.sessions() as session:
        _check_lines(session, user, warehouse_id, lines)

    def callback(session):
        begin_write(session)
        at = now(session, fallback)
        order = MaterialIssueOrder(order_no=next_no("KIT"), warehouse_id=warehouse_id,
                                   issued_by_id=user.id, reason_text=reason, issued_at=at, version=0)
        session.add(order)
        session.flush()
        added = []
        for line in lines:
            added.append(_append_line(session, order, line, user, at))
        record_audit(session, actor_id=user.id, action="KIT_ISSUE",
                     parameters={"orderNo": order.order_no, "lines": added},
                     before_state={"lines": len(lines)}, after_state={"issueOrderId": order.id},
                     occurred_at=at)
        return order.id

    order_id = run_atomic(database.sessions, callback)
    return _result(database, user, order_id)


def _append_line(session, order, line, user, at):
    inventory = session.get(Inventory, line["inventoryId"])
    if inventory.version != line["version"]:
        raise AppError("VERSION_CONFLICT", "库存已变化，请刷新后重新提交整单。")
    before = inventory.on_hand
    if before < line["quantity"]:
        raise AppError("STOCK_INSUFFICIENT", "存在库存不足的物资，整单未生效。")
    if not cas_stock_delta(session, inventory_id=inventory.id,
                           expected_version=line["version"], delta=-line["quantity"]):
        raise AppError("VERSION_CONFLICT", "库存已变化，请刷新后重新提交整单。")
    detail = MaterialIssue(issue_no=next_no("ISS"), inventory_id=inventory.id, quantity=line["quantity"],
                           issued_by_id=user.id, issue_order_id=order.id, reason_text=order.reason_text,
                           issued_at=at, version=0)
    session.add(detail)
    session.flush()
    record_movement(session, inventory_id=inventory.id, item_id=inventory.item_id,
                    movement_type="ISSUE", business_no=detail.issue_no, quantity=line["quantity"],
                    before=before, after=before - line["quantity"], actor_id=user.id, occurred_at=at)
    return {"inventoryId": inventory.id, "quantity": line["quantity"], "issueNo": detail.issue_no}


def _result(database, user, order_id):
    with database.sessions() as session:
        order = session.get(MaterialIssueOrder, order_id)
        details = _load_lines(session, order_id)
        return {"order": order_json(session, order, user),
                "lines": [line_json(session, row, session.get(Inventory, row.inventory_id), user)
                          for row in details],
                "inventories": [inventory_json(session, session.get(Inventory, row.inventory_id), user)
                                for row in details]}


def return_kit(database, fallback, user, order_id, order_version, lines):
    with database.sessions() as session:
        order = _readable_order(session, user, order_id)
        if user.role == "REPORTER":
            raise AppError("NO_PERMISSION", "申请查看人不能办理退回。")
        if user.role not in MANAGERS and order.issued_by_id != user.id:
            raise AppError("NO_PERMISSION", "只能退回本人领用的套料。")
        if order.returned_at is not None:
            raise AppError("ISSUE_ALREADY_RETURNED", "该套料父单已整单退回。")
        details = [{"id": row.id, "inventoryId": row.inventory_id, "quantity": row.quantity,
                    "issueNo": row.issue_no} for row in _load_lines(session, order_id)]
        versions = _match_return_lines(details, lines)
        order_no = order.order_no

    def callback(session):
        begin_write(session)
        at = now(session, fallback)
        updated = session.execute(update(MaterialIssueOrder).where(
            MaterialIssueOrder.id == order_id, MaterialIssueOrder.version == order_version,
            MaterialIssueOrder.returned_at.is_(None)).values(returned_at=at,
                                                             version=MaterialIssueOrder.version + 1))
        if updated.rowcount != 1:
            raise AppError("VERSION_CONFLICT", "单据已变化，请刷新后重新提交。")
        for row in details:
            _restore_line(session, row, versions[row["inventoryId"]], user, at)
        record_audit(session, actor_id=user.id, action="KIT_RETURN",
                     parameters={"issueOrderId": order_id, "orderNo": order_no},
                     before_state={"version": order_version}, after_state={"returnedAt": at.isoformat()},
                     occurred_at=at)

    run_atomic(database.sessions, callback)
    return _result(database, user, order_id)


def _restore_line(session, row, inventory_version, user, at):
    inventory = session.get(Inventory, row["inventoryId"])
    before = inventory.on_hand
    if not cas_stock_delta(session, inventory_id=row["inventoryId"],
                           expected_version=inventory_version, delta=row["quantity"]):
        raise AppError("VERSION_CONFLICT", "库存已变化，请刷新后重新提交。")
    closed = session.execute(update(MaterialIssue).where(
        MaterialIssue.id == row["id"], MaterialIssue.returned_at.is_(None)).values(
        returned_at=at, version=MaterialIssue.version + 1))
    if closed.rowcount != 1:
        raise AppError("ISSUE_ALREADY_RETURNED", "该套料明细已退回。")
    record_movement(session, inventory_id=row["inventoryId"], item_id=inventory.item_id,
                    movement_type="RETURN", business_no=row["issueNo"], quantity=row["quantity"],
                    before=before, after=before + row["quantity"], actor_id=user.id, occurred_at=at)


def _match_return_lines(details, lines):
    """The submitted set must equal the original lines; input order is irrelevant."""
    expected = {row["inventoryId"] for row in details}
    submitted = {line["inventoryId"] for line in lines}
    if submitted != expected or len(submitted) != len(lines):
        raise _invalid("退回行须与原单明细完全一致。")
    return {line["inventoryId"]: line["inventoryVersion"] for line in lines}


def _readable_order(session, user, order_id):
    order = session.get(MaterialIssueOrder, order_id)
    if order is None:
        raise AppError("ISSUE_ORDER_NOT_FOUND", "套料父单不存在。")
    check_warehouse(session, user, order.warehouse_id)
    if user.role not in MANAGERS and order.issued_by_id != user.id:
        raise AppError("NO_PERMISSION", "无权访问该套料父单。")
    return order


def list_kits(database, user, *, mine=False, warehouse_id=None, status=None):
    with database.sessions() as session:
        statement = select(MaterialIssueOrder).where(
            MaterialIssueOrder.warehouse_id.in_(warehouse_scope(session, user)))
        if warehouse_id is not None:
            statement = statement.where(MaterialIssueOrder.warehouse_id == warehouse_id)
        if mine or user.role not in MANAGERS:
            statement = statement.where(MaterialIssueOrder.issued_by_id == user.id)
        items = []
        for order in session.scalars(statement.order_by(MaterialIssueOrder.id.desc())).all():
            actual = STATUS_RETURNED if order.returned_at else STATUS_ISSUED
            if status is None or status == actual:
                items.append(order_json(session, order, user))
        return {"items": items}


def get_kit(database, user, order_id):
    with database.sessions() as session:
        order = _readable_order(session, user, order_id)
        details = _load_lines(session, order_id)
        return {"order": order_json(session, order, user),
                "lines": [line_json(session, row, session.get(Inventory, row.inventory_id), user)
                          for row in details]}
