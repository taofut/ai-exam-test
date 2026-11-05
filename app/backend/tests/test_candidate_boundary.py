import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect


ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def app(tmp_path):
    from materialops.config import Settings
    from materialops.main import create_app

    return create_app(Settings(database_url=f"sqlite:///{tmp_path / 'exam.db'}", allow_exam_reset=True))


@pytest.fixture
def client(app, baseline_dataset):
    with TestClient(app) as test_client:
        assert test_client.post("/api/dev/reset", json={"dataset": baseline_dataset}).status_code == 200
        yield test_client


@pytest.mark.starter
def test_scaffold_does_not_provision_knowledge_or_runtime_foundations(client, app):
    tables = set(inspect(app.state.database.engine).get_table_names())
    assert "t_kb_doc" not in tables
    assert not hasattr(app.state, "sessions")
    assert not hasattr(app.state, "confirmations")


def test_public_dataset_contains_only_organizer_owned_baseline():
    dataset = json.loads((ROOT / "resources" / "demo" / "seed-data.json").read_text(encoding="utf-8"))
    assert "kbDocs" not in dataset


@pytest.mark.starter
def test_runtime_and_knowledge_routes_are_not_implemented_by_scaffold(client):
    assert client.get("/api/kb/docs/1", headers={"X-User": "SYS-001"}).status_code == 422
    assert client.get("/api/demo/stream-fixture", headers={"X-User": "SYS-001"}).status_code == 422
