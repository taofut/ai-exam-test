"""Read-only history projection and documented candidate-table column adapter.

The contract fixes the table name, not its columns. Candidates choosing other
columns should update ISSUE_COLUMNS; queries and fixture import share this map.
"""
from sqlalchemy import MetaData, Table, inspect, select

from materialops.errors import AppError
from materialops.models import FixtureHistory
from materialops.services.clock import iso, utc

ISSUE_COLUMNS = {
    "id": ("id",), "issueNo": ("issue_no", "issueNo"),
    "inventoryId": ("inventory_id", "inventoryId"), "quantity": ("quantity",),
    "issuedById": ("issued_by_id", "issuedById"), "reasonText": ("reason_text", "reasonText"),
    "issuedAt": ("issued_at", "issuedAt"), "returnedAt": ("returned_at", "returnedAt"),
    "version": ("version",), "issueOrderId": ("issue_order_id", "issueOrderId"),
}


def candidate_table(connection):
    if not inspect(connection).has_table("t_material_issue"):
        return None
    return Table("t_material_issue", MetaData(), autoload_with=connection)


def column_map(table):
    result = {}
    for public, choices in ISSUE_COLUMNS.items():
        selected = next((name for name in choices if name in table.c), None)
        if selected:
            result[public] = selected
        elif public not in {"reasonText", "issueOrderId"}:
            raise AppError("VALIDATION_ERROR", f"请按考生领用表列名更新 services/history.py 的 ISSUE_COLUMNS：缺少 {public} 映射。")
    return result


def read_history(session):
    table = candidate_table(session.connection())
    if table is None:
        return [{"issueOrderId": None, **row.payload} for row in session.scalars(select(FixtureHistory).order_by(FixtureHistory.id)).all()]
    mapping = column_map(table)
    rows = []
    for row in session.execute(select(table)).mappings():
        result = {public: row[column] for public, column in mapping.items()}
        result.setdefault("reasonText", "")
        result.setdefault("issueOrderId", None)
        for key in ("issuedAt", "returnedAt"):
            if result[key] is not None:
                result[key] = iso(result[key])
        rows.append(result)
    return rows


def seed_history(connection, records):
    table = candidate_table(connection)
    if table is None:
        return False
    mapping = column_map(table)
    rows = []
    for record in records:
        row = {}
        for public, column in mapping.items():
            value = record.get(public, "" if public == "reasonText" else None)
            if public in {"issuedAt", "returnedAt"} and value is not None:
                value = utc(value)
                if not isinstance(table.c[column].type.python_type, type):
                    value = iso(value)
                elif table.c[column].type.python_type is str:
                    value = iso(value)
            row[column] = value
        rows.append(row)
    if rows:
        connection.execute(table.insert(), rows)
    return True

