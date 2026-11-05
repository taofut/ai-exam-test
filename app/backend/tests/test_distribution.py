"""Release regressions: shared queries, startup and existing-data transitions."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from materialops.config import Settings
from materialops.database import Database
from materialops.main import create_app
from materialops.seed import default_dataset, reset_dataset
from materialops.services.history import read_history


def test_stats_separate_materials_and_units(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'stats.db'}"))
    dataset = default_dataset()
    dataset["materialIssues"] = [
        {"id": 1, "issueNo": "MODULE", "inventoryId": 8101, "quantity": 3,
         "issuedById": 7103, "issuedAt": dataset["now"], "returnedAt": None, "version": 0},
        {"id": 2, "issueNo": "CABLE", "inventoryId": 8113, "quantity": 2,
         "issuedById": 7103, "issuedAt": dataset["now"], "returnedAt": dataset["now"], "version": 1},
    ]
    with TestClient(app) as client:
        assert client.post('/api/dev/reset', json={"dataset": dataset}).status_code == 200
        params = {"period": "TODAY", "warehouseId": 4101}
        headers = {"X-User": "BD-DISPATCH"}
        result = client.get('/api/material-issues/stats', params=params, headers=headers).json()
        assert result["totalQuantity"] is None
        assert sorted((g["unit"], g["quantity"]) for g in result["groups"]) == [("个", 3), ("条", 2)]
        assert all({"itemId", "itemNo", "name", "unit", "quantity"} <= g.keys() for g in result["groups"])
        selected = client.get('/api/material-issues/stats', params={**params, "itemId": 5101}, headers=headers).json()
        assert selected["totalQuantity"] == 3
        assert len(selected["groups"]) == 1


@pytest.fixture
def transition_database(tmp_path, baseline_dataset):
    from alembic import command
    from alembic.config import Config
    from materialops.config import BACKEND_ROOT
    database = Database(f"sqlite:///{tmp_path / 'transition.db'}")
    # Model an existing pre-timed database with a candidate-created issue table.
    config = Config(str(BACKEND_ROOT / 'alembic.ini'))
    config.set_main_option('script_location', str(BACKEND_ROOT / 'alembic'))
    config.set_main_option('sqlalchemy.url', database.url)
    with database.engine.connect() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, '0003_candidate_owned_foundations')
    reset_dataset(database, baseline_dataset)
    with database.engine.begin() as conn:
        conn.execute(text("CREATE TABLE t_material_issue (id INTEGER PRIMARY KEY, issue_no TEXT UNIQUE NOT NULL, inventory_id INTEGER REFERENCES t_inventory(id) NOT NULL, quantity INTEGER NOT NULL, issued_by_id INTEGER REFERENCES t_user(id) NOT NULL, reason_text TEXT NOT NULL, issued_at DATETIME NOT NULL, returned_at DATETIME, version INTEGER NOT NULL, issue_order_id INTEGER)"))
    yield database
    database.engine.dispose()


@pytest.mark.starter
def test_migration_backfills_history_once_without_changing_stock(transition_database):
    database = transition_database
    database.migrate()
    with database.sessions() as session:
        history = read_history(session)
        assert len(history) == 20
        assert all(row["issueOrderId"] is None for row in history)
    with database.engine.begin() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM t_stock_movement')).scalar() == 26
        assert conn.execute(text('SELECT on_hand, version FROM t_inventory WHERE id=10001')).one() == (8, 8)
        assert conn.execute(text('SELECT COUNT(*) FROM t_fixture_history')).scalar() == 0
        conn.execute(text("UPDATE t_material_issue SET reason_text='candidate change', version=9 WHERE id=5001"))
        conn.execute(text('UPDATE t_inventory SET on_hand=7, version=9 WHERE id=10001'))
    database.migrate()
    with database.engine.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM t_material_issue')).scalar() == 20
        assert conn.execute(text('SELECT COUNT(*) FROM t_stock_movement')).scalar() == 26
        assert conn.execute(text('SELECT reason_text, version FROM t_material_issue WHERE id=5001')).one() == ('candidate change', 9)
        assert conn.execute(text('SELECT on_hand, version FROM t_inventory WHERE id=10001')).one() == (7, 9)


@pytest.mark.starter
def test_backfill_failure_rolls_back_history_and_movements(transition_database):
    database = transition_database
    with database.engine.begin() as conn:
        conn.execute(text("CREATE TRIGGER reject_import BEFORE INSERT ON t_stock_movement BEGIN SELECT RAISE(ABORT, 'test import failure'); END"))
    with pytest.raises(Exception, match='test import failure'):
        database.migrate()
    with database.engine.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM t_material_issue')).scalar() == 0
        assert conn.execute(text('SELECT COUNT(*) FROM t_fixture_history')).scalar() == 20
        assert conn.execute(text('SELECT COUNT(*) FROM t_stock_movement')).scalar() == 0
        assert conn.execute(text('SELECT on_hand, version FROM t_inventory WHERE id=10001')).one() == (8, 8)


@pytest.mark.starter
def test_backfill_preserves_existing_history_changes(transition_database, baseline_dataset):
    from materialops.services.history import seed_history

    database = transition_database
    with database.engine.begin() as conn:
        seed_history(conn, baseline_dataset['materialIssues'])
        conn.execute(text("UPDATE t_material_issue SET reason_text='already updated', version=7 WHERE id=5001"))
    database.migrate()
    with database.engine.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM t_material_issue')).scalar() == 20
        assert conn.execute(text('SELECT reason_text, version FROM t_material_issue WHERE id=5001')).one() == ('already updated', 7)


@pytest.mark.starter
def test_backfill_refuses_conflicting_candidate_identity(transition_database, baseline_dataset):
    from materialops.errors import AppError
    from materialops.services.history import seed_history

    database = transition_database
    record = {**baseline_dataset['materialIssues'][0], 'issueNo': 'CANDIDATE-COLLISION'}
    with database.engine.begin() as conn:
        seed_history(conn, [record])
    with pytest.raises(AppError, match='身份冲突'):
        database.migrate()
    with database.engine.connect() as conn:
        assert conn.execute(text('SELECT issue_no FROM t_material_issue')).scalar() == 'CANDIDATE-COLLISION'
        assert conn.execute(text('SELECT COUNT(*) FROM t_fixture_history')).scalar() == 20
        assert conn.execute(text('SELECT COUNT(*) FROM t_stock_movement')).scalar() == 0


def test_initialized_seed_works_with_reset_disabled(tmp_path, baseline_dataset, monkeypatch):
    from materialops import cli

    settings = Settings(database_url=f"sqlite:///{tmp_path / 'closed.db'}", allow_exam_reset=False)
    database = Database(settings.database_url)
    database.migrate()
    reset_dataset(database, baseline_dataset)
    with database.engine.begin() as conn:
        conn.execute(text('UPDATE t_inventory SET on_hand=7, version=9 WHERE id=10001'))
    monkeypatch.setattr(cli, 'settings', settings)
    monkeypatch.setattr('sys.argv', ['cli', 'seed'])
    cli.main()
    with database.engine.connect() as conn:
        assert conn.execute(text('SELECT on_hand, version FROM t_inventory WHERE id=10001')).one() == (7, 9)
    monkeypatch.setattr('sys.argv', ['cli', 'reset'])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    database.engine.dispose()


def test_reset_disabled_does_not_initialize_empty_database(tmp_path, monkeypatch):
    from materialops import cli

    settings = Settings(database_url=f"sqlite:///{tmp_path / 'empty.db'}", allow_exam_reset=False)
    monkeypatch.setattr(cli, 'settings', settings)
    monkeypatch.setattr('sys.argv', ['cli', 'seed'])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
