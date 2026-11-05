"""Validate an entire public dataset before touching the independent exam database."""
import json
from collections import defaultdict

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from sqlalchemy import MetaData, Table, delete, inspect, select

from materialops.config import RESOURCES_ROOT
from materialops.errors import AppError
from materialops.models import Dept, User, Warehouse, Item, Inventory, FixtureHistory, ExamClock, StockMovement
from materialops.services.clock import stored_utc, utc
from materialops.services.history import candidate_table, column_map, seed_history

SCHEMA = json.loads((RESOURCES_ROOT / "schemas" / "dataset.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def default_dataset():
    path = RESOURCES_ROOT / 'demo/material-kit-dataset.json'
    return json.loads(path.read_text(encoding='utf-8'))


def invalid(message):
    raise AppError("VALIDATION_ERROR", message)


def validate_dataset(dataset):
    try:
        VALIDATOR.validate(dataset)
    except ValidationError as exc:
        invalid(f"数据集结构错误：{exc.message}")
    maps = {}
    for key in ("depts", "users", "warehouses", "items", "inventories", "materialIssues"):
        rows = dataset[key]
        ids = [row["id"] for row in rows]
        if len(ids) != len(set(ids)):
            invalid(f"{key} ID 重复。")
        maps[key] = {row["id"]: row for row in rows}
    for key, field in (("users", "employeeNo"), ("items", "itemNo"), ("materialIssues", "issueNo")):
        values = [row[field] for row in dataset[key]]
        if len(values) != len(set(values)):
            invalid(f"{field} 重复。")

    def link(entity, identifier, message):
        if identifier not in maps[entity]:
            invalid(message)
        return maps[entity][identifier]

    for dept in dataset["depts"]:
        seen = {dept["id"]}
        parent = dept["parentId"]
        while parent is not None:
            if parent in seen:
                invalid("部门树存在环。")
            seen.add(parent)
            parent = link("depts", parent, "部门上级不存在。")["parentId"]
    for user in dataset["users"]:
        link("depts", user["deptId"], "用户部门不存在。")
    for warehouse in dataset["warehouses"]:
        link("depts", warehouse["deptId"], "仓库部门不存在。")
    for item in dataset["items"]:
        if item["targetStock"] < item["reorderPoint"]:
            invalid("物资目标库存不能低于补货点。")
    pairs = set()
    for inventory in dataset["inventories"]:
        warehouse = link("warehouses", inventory["warehouseId"], "库存仓库不存在。")
        item = link("items", inventory["itemId"], "库存物资不存在。")
        pair = (warehouse["id"], item["id"])
        if pair in pairs:
            invalid("库存仓库和物资组合重复。")
        pairs.add(pair)
    now = utc(dataset["now"])
    for issue in dataset["materialIssues"]:
        link("inventories", issue["inventoryId"], "领用库存不存在。")
        link("users", issue["issuedById"], "领用用户不存在。")
        issued_at = utc(issue["issuedAt"])
        if issued_at > now:
            invalid("领用时间不能晚于数据集时钟。")
        if issue["returnedAt"] is not None and not issued_at <= utc(issue["returnedAt"]) <= now:
            invalid("退回时间须在领用与数据集时钟之间。")
    return maps


def reset_dataset(database, dataset, *, invalidate_tokens=lambda: None):
    maps = validate_dataset(dataset)
    with database.engine.begin() as connection:
        candidate = candidate_table(connection)
        if candidate is not None:
            column_map(candidate)  # validate the extension before deleting anything
        metadata = MetaData()
        metadata.reflect(bind=connection)
        # All exam tables are cleared in FK dependency order, while Schema survives.
        tables = [table for table in metadata.sorted_tables if table.name != "alembic_version"]
        for table in reversed(tables):
            if table.name != "t_dept":
                connection.execute(delete(table))
        connection.execute(Dept.__table__.update().values(parent_id=None))
        connection.execute(delete(Dept))
        for row in dataset["depts"]:
            connection.execute(Dept.__table__.insert().values(id=row["id"], name=row["name"], parent_id=None))
        for row in dataset["depts"]:
            connection.execute(Dept.__table__.update().where(Dept.id == row["id"]).values(parent_id=row["parentId"]))
        for row in dataset["users"]:
            connection.execute(User.__table__.insert().values(id=row["id"], employee_no=row["employeeNo"], name=row["name"], role=row["role"], dept_id=row["deptId"]))
        for row in dataset["warehouses"]:
            connection.execute(Warehouse.__table__.insert().values(id=row["id"], name=row["name"], dept_id=row["deptId"]))
        for row in dataset["items"]:
            connection.execute(Item.__table__.insert().values(id=row["id"], item_no=row["itemNo"], name=row["name"], unit=row["unit"], reorder_point=row["reorderPoint"], target_stock=row["targetStock"]))
        for row in dataset["inventories"]:
            connection.execute(Inventory.__table__.insert().values(id=row["id"], warehouse_id=row["warehouseId"], item_id=row["itemId"], on_hand=row["onHand"], version=row["version"]))
        if seed_history(connection, dataset["materialIssues"]):
            seed_movements(connection, dataset, maps)
        else:
            for row in dataset["materialIssues"]:
                connection.execute(FixtureHistory.__table__.insert().values(id=row["id"], payload=row))
        connection.execute(ExamClock.__table__.insert().values(id=1, now=utc(dataset["now"])))
    invalidate_tokens()
    return {"status": "ok", "now": dataset["now"], "counts": {key: len(value) for key, value in dataset.items() if isinstance(value, list)}}


def backfill_fixture_history(connection):
    """Consume the seed projection atomically after the candidate adds its table.

    Existing matching identities are preserved, including subsequent returns.
    Conflicting identities abort the import; no business data is overwritten.
    The caller owns the transaction and serializes this startup import.
    """
    table = candidate_table(connection)
    if table is None:
        return
    records = list(connection.execute(select(FixtureHistory.payload)).scalars())
    if not records:
        return
    mapping = column_map(table)
    existing = list(connection.execute(select(table)).mappings())
    by_id = {row[mapping["id"]]: row for row in existing}
    by_no = {row[mapping["issueNo"]]: row for row in existing}
    missing = []
    for record in records:
        previous = by_id.get(record["id"])
        numbered = by_no.get(record["issueNo"])
        if previous is None and numbered is None:
            missing.append(record)
            continue
        if previous is None or numbered is None or any(
            previous[mapping[field]] != record[field]
            for field in ("id", "issueNo", "inventoryId", "quantity", "issuedById")
        ) or stored_utc(previous[mapping["issuedAt"]]) != utc(record["issuedAt"]):
            invalid("预置历史与领用表身份冲突，请核对迁移映射；未覆盖已有记录。")
    seed_history(connection, missing)
    inventories = {row.id: {"itemId": row.item_id} for row in connection.execute(select(Inventory.__table__))}
    seed_movements(connection, {"materialIssues": records}, {"inventories": inventories})
    connection.execute(delete(FixtureHistory))


def seed_movements(connection, dataset, maps):
    events = defaultdict(list)
    for issue in dataset["materialIssues"]:
        events[issue["inventoryId"]].append((utc(issue["issuedAt"]), "ISSUE", issue))
        if issue["returnedAt"]:
            events[issue["inventoryId"]].append((utc(issue["returnedAt"]), "RETURN", issue))
    existing = set(connection.execute(select(StockMovement.business_no, StockMovement.movement_type)).all())
    for inventory_id, timeline in events.items():
        inventory = maps["inventories"][inventory_id]
        for when, kind, issue in sorted(timeline, key=lambda event: (event[0], event[2]["id"], event[1])):
            if (issue["issueNo"], kind) in existing:
                continue
            # The public final snapshot does not describe historical balances.
            connection.execute(StockMovement.__table__.insert().values(inventory_id=inventory_id, item_id=inventory["itemId"], movement_type=kind, business_no=issue["issueNo"], quantity=issue["quantity"], before_on_hand=None, after_on_hand=None, actor_id=issue["issuedById"], occurred_at=when))

