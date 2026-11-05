import copy
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[3]


def test_package_is_available():
    assert importlib.util.find_spec("materialops.main") is not None


@pytest.fixture
def app(tmp_path, monkeypatch):
    from materialops.config import Settings
    from materialops.main import create_app

    return create_app(Settings(database_url=f"sqlite:///{tmp_path / 'exam.db'}", allow_exam_reset=True))


@pytest.fixture
def client(app, baseline_dataset):
    with TestClient(app) as client:
        response = client.post("/api/dev/reset", json={"dataset": baseline_dataset})
        assert response.status_code == 200, response.text
        yield client


def headers(employee="SYS-001"):
    return {"X-User": employee}


def snapshot(app):
    with app.state.database.engine.connect() as conn:
        return {table: conn.execute(text(f'SELECT * FROM "{table}" ORDER BY 1')).fetchall()
                for table in inspect(conn).get_table_names()}


@pytest.mark.starter
def test_health_and_baseline_leave_candidate_tables_absent(client, app):
    assert client.get("/health").json() == {"status": "ok"}
    tables = set(inspect(app.state.database.engine).get_table_names())
    assert {"t_dept", "t_user", "t_inventory", "t_stock_movement", "t_ai_call_log"} <= tables
    assert "t_kb_doc" not in tables
    assert "t_material_issue" in tables
    assert not {"t_request_result", "t_stock_transfer"} & tables
    assert len(client.get("/api/material-issues", headers=headers()).json()["items"]) == 20


def test_identity_is_resolved_server_side(client):
    users = client.get("/api/session/users").json()
    assert len(users) == 14
    assert set(users[0]) == {"id", "employeeNo", "name", "role", "deptId", "deptName"}
    assert client.get("/api/session/me").json()["code"] == "AUTH_REQUIRED"
    assert client.get("/api/session/me", headers=headers("unknown")).json()["code"] == "AUTH_INVALID"
    assert client.get("/api/session/me", headers=headers("OPS-E001")).json()["role"] == "ENGINEER"


def test_inventory_filters_and_correct_scope_branches(client):
    result = client.get("/api/inventories?deptId=1", headers=headers("OPS-D001")).json()["items"]
    assert {row["warehouseId"] for row in result} == {101, 102}
    result = client.get("/api/inventories?deptId=1", headers=headers("OPS-E001")).json()["items"]
    assert {row["warehouseId"] for row in result} == {101}
    assert client.get("/api/inventories?warehouseId=201", headers=headers("SITE-R001")).json() == {"items": []}
    assert client.get("/api/inventories/20001", headers=headers("OPS-E001")).status_code == 403
    low = client.get("/api/inventories?belowReorderPoint=true", headers=headers()).json()["items"]
    assert {row["id"] for row in low} == {10001, 20001, 30001, 40001}


def test_false_low_stock_filter_does_not_exclude_regular_inventory(client):
    assert len(client.get("/api/inventories?belowReorderPoint=false", headers=headers()).json()["items"]) == 8


def test_warehouse_selector_only_contains_visible_inventory_warehouses(client):
    dataset = json.loads((ROOT / "resources/demo/seed-data.json").read_text(encoding="utf-8"))
    dataset["warehouses"].append({"id": 103, "name": "空备件仓", "deptId": 1})
    assert client.post("/api/dev/reset", json={"dataset": dataset}).status_code == 200
    for employee, expected in [("SYS-001", {101, 102, 201, 202, 301, 302, 401, 402}), ("OPS-D001", {101, 102}), ("OPS-E001", {101})]:
        response = client.get("/api/warehouses", headers=headers(employee))
        assert response.status_code == 200
        assert {row["id"] for row in response.json()["items"]} == expected


def test_issues_own_only_and_mine_filter(client):
    own = client.get("/api/material-issues?warehouseId=201", headers=headers("OPS-E001")).json()["items"]
    assert own == []
    assert {row["issuedById"] for row in client.get("/api/material-issues?mine=true", headers=headers("OPS-D001")).json()["items"]} == set()
    rows = client.get("/api/material-issues?status=RETURNED", headers=headers()).json()["items"]
    assert len(rows) == 6 and all(row["returnedAt"] for row in rows)


@pytest.fixture
def moved_engineer_history(client):
    dataset = json.loads((ROOT / "resources/demo/seed-data.json").read_text(encoding="utf-8"))
    next(user for user in dataset["users"] if user["id"] == 3)["deptId"] = 2
    assert client.post("/api/dev/reset", json={"dataset": dataset}).status_code == 200


def test_own_history_does_not_grant_return_permission_outside_current_department(client, moved_engineer_history):
    response = client.get("/api/material-issues/5001", headers=headers("OPS-E001"))
    assert response.status_code == 200
    record = response.json()
    assert record["permissions"]["canReturn"] is False
    assert record["version"] == 0
    assert "onHand" not in record and "inventory" not in record
    assert client.get("/api/inventories/10001", headers=headers("OPS-E001")).status_code == 403
    assert client.get("/api/material-issues/5009", headers=headers("OPS-E001")).status_code == 403


def test_return_checks_current_warehouse_scope_before_pending_service(client, app, moved_engineer_history):
    before = snapshot(app)
    response = client.post("/api/material-issues/5001/return", json={"issueVersion": 0, "inventoryVersion": 8, "requestId": "cross-department-return"}, headers=headers("OPS-E001"))
    assert response.status_code == 403 and response.json()["code"] == "NO_PERMISSION"
    assert snapshot(app) == before


@pytest.mark.parametrize("query", ["period=THIS_WEEK", "period=LAST_WEEK", "groupBy=WAREHOUSE"])
def test_removed_statistics_modes_are_not_exposed(client, query):
    response = client.get("/api/material-issues/stats?" + query, headers=headers())
    assert response.status_code == 400
    assert response.json()["code"] == "QUERY_ARGUMENT_INVALID"


def test_whitelisted_tools_reuse_queries_and_reject_sql(client):
    inventory = client.get("/api/inventories?deptId=1", headers=headers("OPS-D001")).json()
    tool = client.post("/api/tools/inventory_query", json={"deptId": 1}, headers=headers("OPS-D001"))
    assert tool.json() == inventory
    bad = client.post("/api/tools/inventory_query", json={"sql": "SELECT * FROM t_user"}, headers=headers())
    assert bad.status_code == 400 and bad.json()["code"] == "QUERY_ARGUMENT_INVALID"
    assert client.post("/api/tools/kb_answer", json={"query": "电源"}, headers=headers()).status_code == 400


@pytest.mark.parametrize("field,value", [("period", []), ("period", {}), ("groupBy", []), ("groupBy", {})])
def test_tool_enum_rejects_objects_without_internal_error(client, field, value):
    payload = {"period": "TODAY", field: value}
    response = client.post("/api/tools/issue_stats", json=payload, headers=headers())
    assert response.status_code == 400 and response.json()["code"] == "QUERY_ARGUMENT_INVALID"


@pytest.mark.starter
def test_pending_business_routes_never_write(client, app):
    before = snapshot(app)
    requests = [
        ("/api/inventories/10001/issue", {"quantity": 1, "version": 8, "requestId": "new"}),
        ("/api/material-issues/5001/return", {"issueVersion": 0, "inventoryVersion": 8, "requestId": "back"}),
        ("/api/inventories/10001/ai-replenishment", {}),
        ("/api/inventories/10001/ai-replenishment/1/adopt", {}),
        ("/api/inventories/10001/ai-replenishment/1/adopt-edited", {"suggestedQuantity":2,"reason":"testing","reviewed":True}),
        ("/api/inventories/10001/ai-replenishment/1/reject", {}),
        ("/api/stock-transfers/preview", {"itemId": 1001, "fromWarehouseId":101,"toWarehouseId":102,"quantity":1}),
        ("/api/stock-transfers/confirm", {"confirmToken":"unknown"}),
        ("/api/agent/run", {"message": "查一下设备备件库存"}),
    ]
    for path, body in requests:
        response = client.post(path, json=body, headers=headers())
        assert response.status_code == 501, (path, response.text)
        assert response.json()["code"] in {"NOT_IMPLEMENTED", "SKILL_NOT_IMPLEMENTED"}
    assert snapshot(app) == before


def test_permission_precedes_pending_business_and_spoofing(client, app):
    before = snapshot(app)
    response = client.post("/api/inventories/20001/issue", json={"quantity":1,"version":3,"requestId":"spoof","role":"ADMIN","userId":1}, headers=headers("OPS-E001"))
    assert response.status_code == 403
    for employee in ["OPS-E001", "SITE-R001"]:
        assert client.post("/api/inventories/10001/ai-replenishment", json={}, headers=headers(employee)).status_code == 403
        assert client.post("/api/stock-transfers/confirm", json={"confirmToken":"x"}, headers=headers(employee)).status_code == 403
    assert snapshot(app) == before


@pytest.mark.parametrize("body", [None, [], "invalid", {"quantity": True, "version": 8, "requestId": "x"}, {"quantity": 1, "version": 8, "requestId": " "}])
def test_bad_request_body_is_a_contract_error(client, body):
    response = client.post("/api/inventories/10001/issue", json=body, headers=headers())
    assert response.status_code in {400, 422}
    assert set(response.json()) == {"code", "message"}


def test_invalid_dataset_validation_is_atomic(client, app):
    dataset = json.loads((ROOT / "resources/demo/seed-data.json").read_text(encoding="utf-8"))
    before = snapshot(app)
    mutations = [
        lambda d: d["users"].append(copy.deepcopy(d["users"][0])),
        lambda d: d["depts"][0].update(parentId=5),
        lambda d: d["items"][0].update(targetStock=1),
        lambda d: d["inventories"][0].update(itemId=999),
        lambda d: d["materialIssues"][0].update(issuedAt="2026-10-13T00:00:00Z"),
        lambda d: d["users"][0].update(deptId=999),
    ]
    for mutate in mutations:
        invalid = copy.deepcopy(dataset)
        mutate(invalid)
        response = client.post("/api/dev/reset", json={"dataset": invalid})
        assert response.status_code == 422, response.text
        assert snapshot(app) == before


def test_clock_rejects_past_and_accepts_future(client):
    response = client.post("/api/dev/clock", json={"now":"2026-10-10T00:00:00Z"})
    assert response.status_code == 422
    assert client.post("/api/dev/clock", json={"now":"2026-10-13T02:00:00+00:00"}).json()["now"] == "2026-10-13T02:00:00Z"


def test_framework_failures_have_contract_envelope(client):
    missing = client.get("/does-not-exist")
    assert missing.status_code == 422 and missing.json()["code"] == "VALIDATION_ERROR"
    method = client.put("/health")
    assert method.status_code == 422 and set(method.json()) == {"code", "message"}


def test_clock_checks_real_existing_audit_timestamp(client, app):
    with app.state.database.engine.begin() as connection:
        connection.execute(text("INSERT INTO t_audit_log (actor_id, action, parameters, before_state, after_state, result, occurred_at) VALUES (1, 'TEST_FAILURE', '{}', '{}', '{}', 'FAILURE', '2026-10-14 02:00:00')"))
    assert client.post("/api/dev/clock", json={"now": "2026-10-13T02:00:00Z"}).status_code == 422
    assert client.post("/api/dev/clock", json={"now": "2026-10-14T02:00:00Z"}).status_code == 200


def test_dev_gate_uses_public_error(tmp_path):
    from materialops.config import Settings
    from materialops.main import create_app

    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'closed.db'}", allow_exam_reset=False))
    with TestClient(app) as closed:
        assert closed.post("/api/dev/reset").json()["code"] == "NO_PERMISSION"


def test_cli_seed_preserves_initialized_exam_data(client, app, monkeypatch, capsys):
    from materialops import cli

    with app.state.database.engine.begin() as connection:
        connection.execute(text("UPDATE t_inventory SET on_hand=7, version=9 WHERE id=10001"))
    before = snapshot(app)
    monkeypatch.setattr(cli, "settings", app.state.settings)
    monkeypatch.setattr("sys.argv", ["materialops.cli", "seed"])
    cli.main()
    assert snapshot(app) == before


def test_cli_reset_explicitly_restores_public_snapshot(client, app, monkeypatch, capsys):
    from materialops import cli

    with app.state.database.engine.begin() as connection:
        connection.execute(text("UPDATE t_inventory SET on_hand=7, version=9 WHERE id=10001"))
    monkeypatch.setattr(cli, "settings", app.state.settings)
    monkeypatch.setattr("sys.argv", ["materialops.cli", "reset", "--dataset", str(ROOT / "resources/demo/seed-data.json")])
    cli.main()
    row = client.get("/api/inventories/10001", headers=headers()).json()
    assert (row["onHand"], row["version"]) == (8, 8)


@pytest.mark.starter
def test_seed_extension_imports_candidate_table_and_preserves_inventory_snapshot(client, app, baseline_dataset):
    with app.state.database.engine.begin() as conn:
        assert inspect(conn).has_table("t_material_issue")
    assert client.post("/api/dev/reset", json={"dataset": baseline_dataset}).status_code == 200
    with app.state.database.engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM t_material_issue")).scalar() == 20
        assert conn.execute(text("SELECT COUNT(*) FROM t_stock_movement")).scalar() == 26
        assert conn.execute(text("SELECT COUNT(*) FROM t_stock_movement WHERE before_on_hand IS NOT NULL OR after_on_hand IS NOT NULL")).scalar() == 0
        assert conn.execute(text("SELECT on_hand FROM t_inventory WHERE id=10001")).scalar() == 8
    assert len(client.get("/api/material-issues", headers=headers()).json()["items"]) == 20


@pytest.mark.xfail(strict=False, reason="T1 preset defect: engineer warehouseId replaces query scope; candidate must repair")
def test_target_engineer_filter_should_intersect_scope(client):
    assert client.get("/api/inventories?warehouseId=201", headers=headers("OPS-E001")).json()["items"] == []


@pytest.mark.xfail(strict=False, reason="T1 preset defect: TODAY uses UTC day instead of Shanghai; candidate must repair")
def test_target_today_should_include_shanghai_midnight_issue(client):
    assert client.get("/api/material-issues/stats?warehouseId=101&itemId=1001&period=TODAY", headers=headers()).json()["totalQuantity"] == 3
