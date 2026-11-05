"""Timed exam provides schema and seed integration, never business answers."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from materialops.config import Settings
from materialops.main import create_app


@pytest.mark.starter
def test_timed_issue_storage_loads_history_without_implementing_writes(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'timed.db'}"))
    with TestClient(app) as client:
        assert client.post('/api/dev/reset').status_code == 200
        tables = set(inspect(app.state.database.engine).get_table_names())
        assert 't_material_issue' in tables
        assert 't_material_issue_order' in tables
        assert 'issue_order_id' in {c['name'] for c in inspect(app.state.database.engine).get_columns('t_material_issue')}
        assert 't_request_result' not in tables
        assert 't_replenishment_draft' not in tables
        with app.state.database.engine.connect() as conn:
            count = conn.execute(text('SELECT count(*) FROM t_material_issue')).scalar()
            stock = conn.execute(text('SELECT on_hand, version FROM t_inventory WHERE id=8101')).one()
        assert count == 22
        with app.state.database.engine.connect() as conn:
            assert conn.execute(text('SELECT count(*) FROM t_material_issue_order')).scalar() == 0
            assert conn.execute(text('SELECT count(*) FROM t_material_issue WHERE issue_order_id IS NOT NULL')).scalar() == 0
        response = client.post('/api/inventories/8101/issue', headers={'X-User':'BD-ENGINEER'}, json={'quantity':2,'version':0,'requestId':'timed-example'})
        assert response.status_code == 501
        with app.state.database.engine.connect() as conn:
            assert conn.execute(text('SELECT count(*) FROM t_material_issue')).scalar() == count
            assert conn.execute(text('SELECT on_hand, version FROM t_inventory WHERE id=8101')).one() == stock


@pytest.mark.starter
def test_timed_issue_request_does_not_require_generic_idempotency_key(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'request.db'}"))
    with TestClient(app) as client:
        assert client.post('/api/dev/reset').status_code == 200
        response = client.post('/api/inventories/8101/issue', headers={'X-User':'BD-ENGINEER'}, json={'quantity':2,'version':0})
        assert response.status_code == 501, response.text

        issue = client.get('/api/material-issues', headers={'X-User':'BD-ENGINEER'}).json()['items'][0]
        response = client.post(f"/api/material-issues/{issue['id']}/return", headers={'X-User':'BD-ENGINEER'}, json={'issueVersion':issue['version'],'inventoryVersion':issue['inventoryVersion']})
        assert response.status_code == 501, response.text


def test_kit_line_query_exposes_structure_but_disables_single_return(tmp_path):
    from datetime import datetime, timezone
    from materialops.models import MaterialIssue, MaterialIssueOrder

    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'kit-query.db'}"))
    with TestClient(app) as client:
        assert client.post('/api/dev/reset').status_code == 200
        with app.state.database.sessions.begin() as session:
            when = datetime(2026, 10, 12, 2, tzinfo=timezone.utc)
            session.add(MaterialIssueOrder(id=9901, order_no='KIT-TEST', warehouse_id=4101,
                issued_by_id=7103, reason_text='', issued_at=when, version=0))
            session.flush()
            session.add(MaterialIssue(id=9902, issue_no='KIT-LINE-TEST', inventory_id=8101,
                quantity=2, issued_by_id=7103, issue_order_id=9901, reason_text='', issued_at=when, version=0))
        row = client.get('/api/material-issues/9902', headers={'X-User': 'BD-ENGINEER'}).json()
        assert row['issueOrderId'] == 9901
        assert row['permissions']['canReturn'] is False
        assert (row['itemNo'], row['unit'], row['warehouseName']) == ('PWR-24-A', '个', '中心备件仓')


@pytest.mark.starter
def test_analysis_result_entry_is_authorized_placeholder(tmp_path):
    from test_scaffold import snapshot

    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'analysis-query.db'}"))
    with TestClient(app) as client:
        assert client.post('/api/dev/reset').status_code == 200
        before = snapshot(app)
        path = '/api/inventories/8101/ai-replenishment/1'
        assert client.get(path).status_code == 401
        assert client.get(path, headers={'X-User': 'BD-REPORTER'}).status_code == 403
        assert client.get(path, headers={'X-User': 'BD-OTHER-D'}).status_code == 403
        response = client.get(path, headers={'X-User': 'BD-DISPATCH'})
        assert response.status_code == 501
        assert snapshot(app) == before


@pytest.mark.starter
def test_kit_migration_preserves_existing_single_issues(tmp_path, baseline_dataset):
    from alembic import command
    from alembic.config import Config
    from materialops.config import BACKEND_ROOT
    from materialops.database import Database
    from materialops.seed import reset_dataset
    database = Database(f"sqlite:///{tmp_path / 'upgrade.db'}")
    try:
        config = Config(str(BACKEND_ROOT / 'alembic.ini'))
        config.set_main_option('script_location', str(BACKEND_ROOT / 'alembic'))
        with database.engine.connect() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, '0004_timed_issue_table')
        reset_dataset(database, baseline_dataset)
        with database.engine.connect() as connection:
            before = connection.execute(text('SELECT id, issue_no, quantity, returned_at FROM t_material_issue ORDER BY id')).all()
            balances = connection.execute(text('SELECT id, on_hand, version FROM t_inventory ORDER BY id')).all()
        database.migrate()
        with database.engine.connect() as connection:
            assert connection.execute(text('SELECT id, issue_no, quantity, returned_at FROM t_material_issue ORDER BY id')).all() == before
            assert connection.execute(text('SELECT id, on_hand, version FROM t_inventory ORDER BY id')).all() == balances
            assert connection.execute(text('SELECT count(*) FROM t_material_issue WHERE issue_order_id IS NOT NULL')).scalar() == 0
            assert any(f['referred_table'] == 't_material_issue_order' for f in inspect(connection).get_foreign_keys('t_material_issue'))
    finally:
        database.engine.dispose()


@pytest.mark.starter
def test_upgrade_keeps_populated_legacy_draft_and_analysis(tmp_path, baseline_dataset):
    from alembic import command
    from alembic.config import Config
    from materialops.config import BACKEND_ROOT
    from materialops.database import Database
    from materialops.seed import reset_dataset

    database = Database(f"sqlite:///{tmp_path / 'legacy-plan.db'}")
    try:
        config = Config(str(BACKEND_ROOT / 'alembic.ini'))
        config.set_main_option('script_location', str(BACKEND_ROOT / 'alembic'))
        with database.engine.connect() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, '0005_timed_kit_structure')
        reset_dataset(database, baseline_dataset)
        with database.engine.begin() as connection:
            connection.execute(text("INSERT INTO t_ai_call_log (id,inventory_id,inventory_version,actor_id,model,prompt_version,duration_ms,decision,created_at) VALUES (1,10001,8,1,'legacy','v1',1,'ADOPTED','2026-10-12 02:00:00')"))
            connection.execute(text("INSERT INTO t_replenishment_draft (id,inventory_id,warehouse_id,item_id,quantity,source_call_id,created_by_id,created_at,status) VALUES (1,10001,101,1001,4,1,1,'2026-10-12 02:00:00','DRAFT')"))
            before = connection.execute(text('SELECT * FROM t_replenishment_draft')).all()
        database.migrate()
        database.migrate()
        with database.engine.connect() as connection:
            assert connection.execute(text('SELECT * FROM t_replenishment_draft')).all() == before
            assert connection.execute(text('SELECT decision FROM t_ai_call_log WHERE id=1')).scalar() == 'ADOPTED'
            assert connection.execute(text('SELECT on_hand,version FROM t_inventory WHERE id=10001')).one() == (8,8)
    finally:
        database.engine.dispose()
