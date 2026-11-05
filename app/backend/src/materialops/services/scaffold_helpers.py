"""Organizer transaction/CAS primitives; business validation remains candidate work."""
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy import update
from sqlalchemy.orm import Session

from materialops.models import Inventory

Result = TypeVar("Result")


def run_atomic(session_factory: Callable[[], Session], callback: Callable[[Session], Result]) -> Result:
    """Run one callback in a fresh transaction; propagate and roll back failures.

Pass ``database.sessions``. The callback adds all relevant rows and must not
commit independently. A successful return is committed by this wrapper.
"""
    with session_factory() as session:
        with session.begin():
            return callback(session)


def cas_stock_delta(session: Session, *, inventory_id: int, expected_version: int, delta: int) -> bool:
    """Conditionally change a balance and increment its version, without commit.

False means no row matched ID, version and nonnegative resulting balance.
The caller chooses the public business error and keeps all dependent changes
inside the same transaction. This method does not grant any permission.
"""
    if type(inventory_id) is not int or inventory_id <= 0:
        raise ValueError("inventory_id must be a positive integer")
    if type(expected_version) is not int or expected_version < 0:
        raise ValueError("expected_version must be a nonnegative integer")
    if type(delta) is not int:
        raise ValueError("delta must be an integer")
    statement = update(Inventory).where(
        Inventory.id == inventory_id,
        Inventory.version == expected_version,
        Inventory.on_hand + delta >= 0,
    ).values(on_hand=Inventory.on_hand + delta, version=Inventory.version + 1)
    return session.execute(statement.execution_options(synchronize_session="fetch")).rowcount == 1
