import pytest
from materialops.database import Database
from materialops.models import Inventory
from materialops.seed import reset_dataset


@pytest.fixture
def database(tmp_path, baseline_dataset):
    database = Database(f"sqlite:///{tmp_path / 'foundations.db'}")
    database.migrate()
    reset_dataset(database, baseline_dataset)
    yield database
    database.engine.dispose()


def stock(database):
    with database.sessions() as session:
        row = session.get(Inventory, 10001)
        return row.on_hand, row.version


def test_atomic_callback_commits_one_unit_and_returns_result(database):
    from materialops.services.scaffold_helpers import run_atomic

    def operation(session):
        row = session.get(Inventory, 10001)
        row.on_hand -= 1
        return "saved"

    assert run_atomic(database.sessions, operation) == "saved"
    assert stock(database) == (7, 8)


def test_atomic_callback_rolls_back_all_changes_when_operation_fails(database):
    from materialops.services.scaffold_helpers import run_atomic

    def operation(session):
        session.get(Inventory, 10001).on_hand = 0
        session.flush()
        raise ValueError("stop")

    with pytest.raises(ValueError, match="stop"):
        run_atomic(database.sessions, operation)
    assert stock(database) == (8, 8)


def test_stock_delta_matches_id_version_and_nonnegative_balance(database):
    from materialops.services.scaffold_helpers import cas_stock_delta, run_atomic

    def operation(session):
        assert cas_stock_delta(session, inventory_id=10001, expected_version=8, delta=-3)
        assert not cas_stock_delta(session, inventory_id=10001, expected_version=8, delta=-1)
        assert not cas_stock_delta(session, inventory_id=10001, expected_version=9, delta=-6)
        assert not cas_stock_delta(session, inventory_id=99999, expected_version=9, delta=2)

    run_atomic(database.sessions, operation)
    assert stock(database) == (5, 9)


def test_stock_delta_does_not_commit_outside_its_callers_transaction(database):
    from materialops.services.scaffold_helpers import cas_stock_delta

    with database.sessions() as session:
        assert cas_stock_delta(session, inventory_id=10001, expected_version=8, delta=4)
        session.rollback()
    assert stock(database) == (8, 8)


def test_stock_delta_keeps_a_loaded_inventory_snapshot_current(database):
    from materialops.services.scaffold_helpers import cas_stock_delta

    with database.sessions() as session:
        row = session.get(Inventory, 10001)
        assert cas_stock_delta(session, inventory_id=10001, expected_version=8, delta=-2)
        assert (row.on_hand, row.version) == (6, 9)
        session.rollback()
    assert stock(database) == (8, 8)


@pytest.mark.parametrize("values", [dict(inventory_id=True, expected_version=8, delta=1), dict(inventory_id=10001, expected_version=-1, delta=1), dict(inventory_id=10001, expected_version=8, delta=False)])
def test_stock_delta_rejects_structural_values_before_query(database, values):
    from materialops.services.scaffold_helpers import cas_stock_delta

    with database.sessions() as session, pytest.raises(ValueError):
        cas_stock_delta(session, **values)
    assert stock(database) == (8, 8)
