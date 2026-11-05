"""Shared T1 ledger helpers: numbering, movements, audit and public serialization."""
from uuid import uuid4

from sqlalchemy import text

from materialops.models import AuditLog, Item, StockMovement, Warehouse
from materialops.services.access import warehouse_scope
from materialops.services.clock import iso

REASON_LIMIT = 500
MANAGERS = frozenset({"ADMIN", "DISPATCHER"})
STATUS_ISSUED, STATUS_RETURNED = "ISSUED", "RETURNED"


def begin_write(session):
    """Take the SQLite write lock up front so concurrent CAS requests queue instead of deadlocking."""
    if session.get_bind().dialect.name == "sqlite":
        session.execute(text("BEGIN IMMEDIATE"))


def next_no(prefix):
    return f"{prefix}-{uuid4().hex[:12].upper()}"


def record_movement(session, *, inventory_id, item_id, movement_type, business_no,
                    quantity, before, after, actor_id, occurred_at):
    session.add(StockMovement(inventory_id=inventory_id, item_id=item_id, movement_type=movement_type,
                              business_no=business_no, quantity=quantity, before_on_hand=before,
                              after_on_hand=after, actor_id=actor_id, occurred_at=occurred_at))


def record_audit(session, *, actor_id, action, parameters, before_state, after_state, occurred_at):
    session.add(AuditLog(actor_id=actor_id, action=action, parameters=parameters, before_state=before_state,
                         after_state=after_state, result="SUCCESS", occurred_at=occurred_at))


def can_return(session, user, *, warehouse_id, issued_by_id, returned):
    """Role matrix for returning the whole original record; state is checked by callers."""
    if returned or user.role == "REPORTER":
        return False
    if warehouse_id not in warehouse_scope(session, user):
        return False
    return user.role in MANAGERS or issued_by_id == user.id


def order_json(session, order, user):
    returned = order.returned_at is not None
    return {"id": order.id, "orderNo": order.order_no, "warehouseId": order.warehouse_id,
            "issuedById": order.issued_by_id, "reasonText": order.reason_text or "",
            "issuedAt": iso(order.issued_at), "returnedAt": iso(order.returned_at), "version": order.version,
            "status": STATUS_RETURNED if returned else STATUS_ISSUED,
            "permissions": {"canReturn": can_return(session, user, warehouse_id=order.warehouse_id,
                                                    issued_by_id=order.issued_by_id, returned=returned)}}


def line_json(session, row, inventory, user):
    """One real detail line; a kit line always points back to its parent record."""
    item = session.get(Item, inventory.item_id)
    warehouse = session.get(Warehouse, inventory.warehouse_id)
    returned = row.returned_at is not None
    allowed = row.issue_order_id is None and can_return(
        session, user, warehouse_id=warehouse.id, issued_by_id=row.issued_by_id, returned=returned)
    return {"id": row.id, "issueNo": row.issue_no, "issueOrderId": row.issue_order_id,
            "inventoryId": row.inventory_id, "quantity": row.quantity,
            "issuedById": row.issued_by_id, "reasonText": row.reason_text or "",
            "issuedAt": iso(row.issued_at), "returnedAt": iso(row.returned_at),
            "status": STATUS_RETURNED if returned else STATUS_ISSUED, "version": row.version,
            "inventoryVersion": inventory.version, "warehouseId": warehouse.id,
            "warehouseName": warehouse.name, "itemId": item.id, "itemNo": item.item_no,
            "itemName": item.name, "unit": item.unit, "permissions": {"canReturn": allowed}}
