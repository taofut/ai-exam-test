import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from materialops.config import EXAM_ROOT, Settings
from materialops.main import create_app
from test_scaffold import snapshot


def starter_app(tmp_path):
    return create_app(Settings(database_url=f"sqlite:///{tmp_path / 'starter.db'}", allow_exam_reset=True))


def test_default_reset_loads_shared_public_dataset(tmp_path):
    app = starter_app(tmp_path)
    data = json.loads((EXAM_ROOT / 'resources/demo/material-kit-dataset.json').read_text(encoding='utf-8'))
    with TestClient(app) as client:
        result = client.post('/api/dev/reset')
        assert result.status_code == 200
        assert result.json()['counts']['inventories'] == len(data['inventories'])
        rows = client.get('/api/inventories', headers={'X-User': 'BD-ADMIN'}).json()['items']
        assert {(r['id'], r['onHand'], r['version']) for r in rows} == {(r['id'], r['onHand'], r['version']) for r in data['inventories']}
        row = next(r for r in rows if r['id'] == 8101)
        item = next(r for r in data['items'] if r['id'] == row['itemId'])
        warehouse = next(r for r in data['warehouses'] if r['id'] == row['warehouseId'])
        assert row['itemNo'] == item['itemNo']
        assert row['deptId'] == warehouse['deptId']
        assert row['deptName'] == next(r['name'] for r in data['depts'] if r['id'] == warehouse['deptId'])


@pytest.mark.starter
def test_kit_entries_authenticate_but_do_not_implement_candidate_rules(tmp_path):
    app = starter_app(tmp_path)
    with TestClient(app) as client:
        assert client.post('/api/dev/reset').status_code == 200
        before = snapshot(app)
        for method, path in [('get','/api/material-issue-orders'), ('post','/api/material-issue-orders'), ('get','/api/material-issue-orders/9201'), ('post','/api/material-issue-orders/9201/return')]:
            assert client.request(method, path).status_code == 401
            response = client.request(method, path, headers={'X-User':'BD-ADMIN'})
            assert response.status_code == 501, response.text
            assert response.json()['code'] == 'NOT_IMPLEMENTED'
        assert snapshot(app) == before
        assert 't_material_issue_order' in inspect(app.state.database.engine).get_table_names()


def test_cli_seed_preserves_inventory_and_history_on_restart(tmp_path, monkeypatch, capsys):
    from materialops import cli
    from materialops.database import Database
    from materialops.models import FixtureHistory
    from materialops.seed import default_dataset
    from materialops.services.history import read_history, seed_history
    from sqlalchemy import text

    configuration = Settings(database_url=f"sqlite:///{tmp_path / 'runtime/data/cli.db'}", allow_exam_reset=True)
    monkeypatch.setattr(cli, 'settings', configuration)
    monkeypatch.setattr('sys.argv', ['cli', 'seed'])
    cli.main()
    database = Database(configuration.database_url)
    try:
        with database.engine.begin() as conn:
            assert conn.execute(text('SELECT on_hand FROM t_inventory WHERE id=8101')).scalar() == 10
            conn.execute(text('UPDATE t_inventory SET on_hand=9, version=1 WHERE id=8101'))
            history = next(row.copy() for row in default_dataset()['materialIssues'] if row['id'] == 9104)
            history.update(id=99001, issueNo='TEST-CONTINUATION-99001', quantity=1)
            if not seed_history(conn, [history]):
                conn.execute(FixtureHistory.__table__.insert().values(id=99001, payload=history))
        for _ in range(3):
            cli.main()
            with database.engine.connect() as conn:
                assert conn.execute(text('SELECT on_hand, version FROM t_inventory WHERE id=8101')).one() == (9, 1)
            with database.sessions() as session:
                records = read_history(session)
                assert len(records) == 23
                actual = next(row for row in records if row['id'] == 99001)
                assert all(actual[key] == value for key, value in history.items())
    finally:
        database.engine.dispose()


def test_error_envelope_only_exposes_line_details_on_kit_routes(tmp_path):
    from materialops.errors import AppError

    app = starter_app(tmp_path)
    detail = {'lineIndex': 1, 'inventoryId': 8110, 'code': 'VERSION_CONFLICT', 'message': 'test fixture'}

    def fail():
        raise AppError('VERSION_CONFLICT', 'test error', details=[detail])

    app.add_api_route('/api/material-issue-orders/test-error', fail)
    app.add_api_route('/api/test-error', fail)
    with TestClient(app) as client:
        # POST avoids the GET /{order_id} placeholder route.
        app.add_api_route('/api/material-issue-orders/test-error', fail, methods=['POST'])
        response = client.post('/api/material-issue-orders/test-error')
        assert response.status_code == 409
        assert response.json()['details'] == [detail]
        assert client.get('/api/test-error').json() == {'code':'VERSION_CONFLICT', 'message':'test error'}


def test_cli_rejects_removed_stage_argument_before_creating_database(tmp_path, monkeypatch):
    from materialops import cli

    path = tmp_path / 'unused.db'
    monkeypatch.setattr(cli, 'settings', Settings(database_url=f'sqlite:///{path}'))
    monkeypatch.setattr('sys.argv', ['cli', 'seed', '--stage', 'T1'])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert not path.exists()
