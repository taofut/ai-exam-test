"""Public conversation entry validates identity and input before candidate work."""
import pytest

from test_scaffold import app, client, headers, snapshot


def test_agent_entry_requires_identity(client):
    assert client.post("/api/agent/run", json={}).status_code == 401


@pytest.mark.parametrize("body", [
    {"message": "text", "sessionId": 3},
    {"message": " "},
    {"message": "text", "confirmToken": False},
    {"message": "text", "sessionId": []},
])
def test_agent_entry_validates_basic_structure(client, body):
    response = client.post("/api/agent/run", json=body, headers=headers())
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.starter
@pytest.mark.parametrize("accept", ["application/json", "text/event-stream"])
def test_agent_entry_does_not_write_or_fake_a_business_result(client, app, accept):
    before = snapshot(app)
    response = client.post("/api/agent/run", json={"message": "查库存", "sessionId": "a"}, headers={**headers(), "Accept": accept})
    assert response.status_code == 501
    assert response.headers['content-type'].startswith('application/json')
    assert response.json()["code"] == "SKILL_NOT_IMPLEMENTED"
    assert snapshot(app) == before
