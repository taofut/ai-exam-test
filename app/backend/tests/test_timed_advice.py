"""T2 regressions: evidence-backed analysis, review gate and degraded backup advice."""
import pytest
from fastapi.testclient import TestClient

from materialops.config import Settings
from materialops.main import create_app
from materialops.seed import default_dataset

DISPATCHER = {"X-User": "BD-DISPATCH"}
ENGINEER = {"X-User": "BD-ENGINEER"}
INVENTORY = 8101  # PWR-24-A at warehouse 4101: onHand 10, reorder 5, target 20


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'advice.db'}", allow_exam_reset=True))
    with TestClient(app) as test_client:
        assert test_client.post("/api/dev/reset", json={"dataset": default_dataset()}).status_code == 200
        yield test_client


def analyze(client, headers, fault=None):
    request_headers = headers if fault is None else {**headers, "X-Model-Fault": fault}
    response = client.post(f"/api/inventories/{INVENTORY}/ai-replenishment", headers=request_headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_analysis_uses_today_scope_visible_knowledge_and_adopts_original(client):
    body = analyze(client, DISPATCHER, fault="low_confidence")
    assert body["decision"] == "PENDING"
    assert (body["degraded"], body["requiresHumanReview"], body["reviewItems"]) == (False, False, [])

    stats = body["context"]["issueStats"]
    assert (stats["period"], stats["quantity"], stats["asOf"]) == ("TODAY", 12, "2026-10-12T02:00:00Z")
    assert "4101" in stats["scope"] and "5101" in stats["scope"]

    documents = {doc["docId"]: doc for doc in body["context"]["knowledge"]}
    # 10106 belongs to another department, 10108 is INACTIVE, 10102 targets another item.
    assert set(documents) == {10101, 10103, 10107}

    suggestion = body["suggestion"]
    assert (suggestion["warehouseId"], suggestion["itemId"], suggestion["suggestedQuantity"]) == (4101, 5101, 10)
    assert (suggestion["confidence"], suggestion["needHuman"]) == (0.35, False)
    reference = suggestion["knowledgeReferences"][0]
    assert (reference["docId"], reference["version"]) == (10101, 1)
    assert reference["quote"] in documents[10101]["content"]

    adopted = client.post(f"/api/inventories/{INVENTORY}/ai-replenishment/{body['callId']}/adopt",
                          headers=DISPATCHER, json={"reviewed": True})
    assert adopted.status_code == 200, adopted.text
    decision = adopted.json()
    assert (decision["decision"], decision["reviewed"], decision["decisionById"]) == ("ADOPTED", True, 7102)
    assert decision["finalSuggestion"] == suggestion
    assert decision["suggestion"] == suggestion

    stored = client.get(f"/api/inventories/{INVENTORY}/ai-replenishment/{body['callId']}", headers=DISPATCHER)
    assert stored.status_code == 200
    assert stored.json()["finalSuggestion"] == suggestion


def test_degraded_analysis_requires_review_and_blocks_unconfirmed_adopt(client):
    body = analyze(client, DISPATCHER, fault="timeout")
    assert (body["degraded"], body["requiresHumanReview"]) == (True, True)
    assert body["reviewItems"] and "timeout" in body["reviewItems"][0].lower()
    # Real stock: max(0, min(500, 20 - 10)).
    assert (body["suggestion"]["suggestedQuantity"], body["suggestion"]["confidence"]) == (10, 0)
    assert body["suggestion"]["needHuman"] is True
    assert body["suggestion"]["knowledgeReferences"] == []

    call_id = body["callId"]
    blocked = client.post(f"/api/inventories/{INVENTORY}/ai-replenishment/{call_id}/adopt",
                          headers=DISPATCHER, json={"reviewed": False})
    assert blocked.status_code == 409 and blocked.json()["code"] == "HUMAN_REVIEW_REQUIRED"
    assert client.get(f"/api/inventories/{INVENTORY}/ai-replenishment/{call_id}",
                      headers=DISPATCHER).json()["decision"] == "PENDING"

    over_limit = client.post(f"/api/inventories/{INVENTORY}/ai-replenishment/{call_id}/adopt-edited",
                             headers=DISPATCHER,
                             json={"suggestedQuantity": 501, "reason": "超上限", "reviewed": True})
    assert over_limit.status_code == 422 and over_limit.json()["code"] == "VALIDATION_ERROR"

    forbidden = client.get(f"/api/inventories/{INVENTORY}/ai-replenishment/{call_id}", headers=ENGINEER)
    assert forbidden.status_code == 403

    confirmed = client.post(f"/api/inventories/{INVENTORY}/ai-replenishment/{call_id}/adopt",
                            headers=DISPATCHER, json={"reviewed": True})
    assert confirmed.status_code == 200, confirmed.text
    assert (confirmed.json()["decision"], confirmed.json()["reviewed"]) == ("ADOPTED", True)
