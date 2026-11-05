"""T1 kit regressions: atomic same-warehouse issue, line-set rejection and whole-kit return."""
import pytest
from fastapi.testclient import TestClient

from materialops.config import Settings
from materialops.main import create_app
from materialops.seed import default_dataset

WAREHOUSE = 4101
ENGINEER = {"X-User": "BD-ENGINEER"}


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'kit.db'}", allow_exam_reset=True))
    with TestClient(app) as test_client:
        assert test_client.post("/api/dev/reset", json={"dataset": default_dataset()}).status_code == 200
        yield test_client


def stock(client, inventory_id):
    return client.get(f"/api/inventories/{inventory_id}", headers=ENGINEER).json()


def today_total(client, item_id):
    response = client.get("/api/material-issues/stats", headers=ENGINEER,
                          params={"warehouseId": WAREHOUSE, "itemId": item_id})
    return response.json()["totalQuantity"]


def kit_payload():
    return {"warehouseId": WAREHOUSE, "reasonText": "夜间抢修", "lines": [
        {"inventoryId": 8101, "quantity": 2, "version": 0},
        {"inventoryId": 8107, "quantity": 1, "version": 3},
    ]}


def test_kit_issue_creates_parent_with_complete_lines_and_deducts_stock_once(client):
    before = today_total(client, 5101)
    response = client.post("/api/material-issue-orders", headers=ENGINEER, json=kit_payload())
    assert response.status_code == 200, response.text
    body = response.json()

    order = body["order"]
    assert order["orderNo"].startswith("KIT-")
    assert (order["warehouseId"], order["status"], order["version"], order["returnedAt"]) == (WAREHOUSE, "ISSUED", 0, None)
    lines = {line["inventoryId"]: line for line in body["lines"]}
    assert len(lines) == 2
    assert {line["issueOrderId"] for line in lines.values()} == {order["id"]}
    assert {(line["quantity"], line["status"]) for line in lines.values()} == {(2, "ISSUED"), (1, "ISSUED")}
    assert all(line["issueNo"].startswith("ISS-") for line in lines.values())

    assert {row["id"]: row["onHand"] for row in body["inventories"]} == {8101: 8, 8107: 3}
    assert stock(client, 8101)["onHand"] == 8
    assert stock(client, 8107)["onHand"] == 3
    # A kit counts once through its lines; the parent record must not add a second time.
    assert today_total(client, 5101) - before == 2


def test_kit_rejects_duplicate_cross_warehouse_and_single_line_sets(client):
    duplicate = {"warehouseId": WAREHOUSE, "lines": [
        {"inventoryId": 8101, "quantity": 1, "version": 0},
        {"inventoryId": 8101, "quantity": 1, "version": 0},
    ]}
    mixed = {"warehouseId": WAREHOUSE, "lines": [
        {"inventoryId": 8101, "quantity": 1, "version": 0},
        {"inventoryId": 8109, "quantity": 1, "version": 0},
    ]}
    single = {"warehouseId": WAREHOUSE, "lines": [{"inventoryId": 8101, "quantity": 1, "version": 0}]}

    for payload in (duplicate, mixed, single):
        response = client.post("/api/material-issue-orders", headers=ENGINEER, json=payload)
        assert response.status_code == 400, response.text
        assert response.json()["code"] == "KIT_LINES_INVALID"

    assert stock(client, 8101)["onHand"] == 10
    assert stock(client, 8109)["onHand"] == 9


def test_kit_return_restores_all_lines_and_rejects_single_child_return(client):
    created = client.post("/api/material-issue-orders", headers=ENGINEER, json=kit_payload()).json()
    order_id = created["order"]["id"]
    lines = [{"inventoryId": line["inventoryId"], "inventoryVersion": line["inventoryVersion"]}
             for line in created["lines"]]

    response = client.post(f"/api/material-issue-orders/{order_id}/return", headers=ENGINEER,
                           json={"orderVersion": created["order"]["version"], "lines": lines})
    assert response.status_code == 200, response.text
    returned = response.json()
    assert returned["order"]["status"] == "RETURNED"
    assert returned["order"]["returnedAt"] == returned["lines"][0]["returnedAt"]
    assert {line["status"] for line in returned["lines"]} == {"RETURNED"}
    assert stock(client, 8101)["onHand"] == 10
    assert stock(client, 8107)["onHand"] == 4

    child = returned["lines"][0]
    single = client.post(f"/api/material-issues/{child['id']}/return", headers=ENGINEER,
                         json={"issueVersion": child["version"], "inventoryVersion": child["inventoryVersion"]})
    assert single.status_code == 409, single.text
    assert single.json()["code"] == "KIT_RETURN_REQUIRED"
