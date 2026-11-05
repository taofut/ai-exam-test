from collections import defaultdict
from datetime import UTC, timedelta, timezone

from sqlalchemy import select

from materialops.errors import AppError
from materialops.models import Dept, Inventory, Item, Warehouse
from materialops.services.access import check_warehouse, subtree, warehouse_scope
from materialops.services.clock import now, utc
from materialops.services.history import read_history
from materialops.services.ledger import MANAGERS, STATUS_ISSUED, STATUS_RETURNED

BEIJING = timezone(timedelta(hours=8))


def inventory_json(session, row, user):
    warehouse = session.get(Warehouse, row.warehouse_id)
    item = session.get(Item, row.item_id)
    visible = row.warehouse_id in warehouse_scope(session, user)
    return {"id": row.id, "warehouseId": row.warehouse_id, "warehouseName": warehouse.name,
            "deptId": warehouse.dept_id, "deptName": session.get(Dept, warehouse.dept_id).name,
            "itemNo": item.item_no,
            "itemId": row.item_id, "itemName": item.name, "unit": item.unit,
            "onHand": row.on_hand, "version": row.version,
            "reorderPoint": item.reorder_point, "targetStock": item.target_stock,
            "permissions": {"canIssue": visible and user.role in MANAGERS | {"ENGINEER"},
                            "canAnalyze": visible and user.role in MANAGERS,
                            "canTransfer": visible and user.role in MANAGERS}}


def list_inventories(session, user, *, deptId=None, warehouseId=None, itemId=None, belowReorderPoint=None):
    # Filters only narrow the authorized scope; they never widen it.
    permitted = warehouse_scope(session, user)
    statement = select(Inventory).join(Warehouse).join(Item).where(Inventory.warehouse_id.in_(permitted))
    if deptId is not None:
        statement = statement.where(Warehouse.dept_id.in_(subtree(session, deptId)))
    if warehouseId is not None:
        statement = statement.where(Inventory.warehouse_id == warehouseId)
    if itemId is not None:
        statement = statement.where(Inventory.item_id == itemId)
    if belowReorderPoint is True:
        statement = statement.where(Inventory.on_hand < Item.reorder_point)
    return {"items": [inventory_json(session, row, user) for row in session.scalars(statement.order_by(Inventory.id)).all()]}


def get_inventory(session, user, inventory_id):
    row = session.get(Inventory, inventory_id)
    if row is None:
        raise AppError("INVENTORY_NOT_FOUND", "库存不存在。")
    check_warehouse(session, user, row.warehouse_id)
    return row


def visible_history(session, user, *, warehouseId=None, itemId=None, status=None, mine=False, stats=False):
    inventory_map = {row.id: row for row in session.scalars(select(Inventory)).all()}
    permitted = warehouse_scope(session, user)
    if warehouseId is not None and warehouseId not in permitted:
        # A filter narrows the current scope; it never reaches outside it.
        return []
    records = []
    for issue in read_history(session):
        inventory = inventory_map[issue["inventoryId"]]
        is_own = issue["issuedById"] == user.id
        if mine and not is_own:
            continue
        if stats:
            # Statistics count every issuer, but only inside the current authorized scope.
            if inventory.warehouse_id not in permitted:
                continue
        elif user.role in {"ENGINEER", "REPORTER"}:
            if not is_own:
                continue
        elif inventory.warehouse_id not in permitted:
            continue
        if warehouseId is not None and inventory.warehouse_id != warehouseId:
            continue
        if itemId is not None and inventory.item_id != itemId:
            continue
        actual_status = STATUS_RETURNED if issue["returnedAt"] else STATUS_ISSUED
        if status is not None and actual_status != status:
            continue
        warehouse = session.get(Warehouse, inventory.warehouse_id)
        item = session.get(Item, inventory.item_id)
        records.append({**issue, "warehouseId": inventory.warehouse_id, "itemId": inventory.item_id,
                        "warehouseName": warehouse.name, "itemName": item.name,
                        "itemNo": item.item_no, "unit": item.unit,
                        "inventoryVersion": inventory.version,
                        "status": actual_status, "reasonText": issue.get("reasonText", ""),
                        "permissions": {"canReturn": actual_status == "ISSUED" and issue.get("issueOrderId") is None and
                            inventory.warehouse_id in permitted and
                            (user.role in MANAGERS or user.role == "ENGINEER" and is_own)}})
    return sorted(records, key=lambda row: (row["issuedAt"], row["id"]), reverse=True)


def get_issue(session, user, issue_id):
    for issue in visible_history(session, user):
        if issue["id"] == issue_id:
            return issue
    if any(row["id"] == issue_id for row in read_history(session)):
        raise AppError("NO_PERMISSION", "无权访问该领用记录。")
    raise AppError("ISSUE_NOT_FOUND", "领用记录不存在。")


def issue_stats(session, user, fallback, *, warehouseId=None, itemId=None, period="TODAY", groupBy="ITEM"):
    clock = now(session, fallback)
    if period != "TODAY" or groupBy != "ITEM":
        raise AppError("QUERY_ARGUMENT_INVALID", "限时版只提供 TODAY 按物资统计。")
    # "Today" is a Beijing calendar day ([00:00, next 00:00) Asia/Shanghai), stored as UTC.
    local_day = clock.astimezone(BEIJING)
    start = local_day.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    end = start + timedelta(days=1)
    quantities = defaultdict(int)
    for issue in visible_history(session, user, warehouseId=warehouseId, itemId=itemId, stats=True):
        issued_at = utc(issue["issuedAt"])
        if start <= issued_at < end and issued_at <= clock:
            quantities[issue["itemId"]] += issue["quantity"]
    groups = []
    for item_id, quantity in sorted(quantities.items()):
        item = session.get(Item, item_id)
        group = {"itemId": item.id, "itemNo": item.item_no, "name": item.name,
                 "unit": item.unit, "quantity": quantity}
        groups.append(group)
    return {"totalQuantity": sum(quantities.values()) if itemId is not None else None, "groups": groups}


