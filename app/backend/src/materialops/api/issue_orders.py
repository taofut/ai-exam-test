"""T1 kit routes: same-warehouse 2-5 line issue, listing, detail and whole-kit return."""
from typing import Any

from fastapi import APIRouter, Body, Header, Query, Request

from materialops.api.validation import integer, object_body
from materialops.errors import AppError
from materialops.services.access import authenticate
from materialops.services.kit import create_kit, get_kit, list_kits, return_kit
from materialops.services.ledger import REASON_LIMIT, STATUS_ISSUED, STATUS_RETURNED

router = APIRouter(prefix='/api/material-issue-orders', tags=['T1 kit — candidate implementation'])

STATUSES = {STATUS_ISSUED, STATUS_RETURNED}


def _lines(body, fields):
    """Structural checks only; kit membership and balances are business checks."""
    lines = body.get("lines")
    if not isinstance(lines, list) or not all(isinstance(line, dict) for line in lines):
        raise AppError("KIT_LINES_INVALID", "lines 须为物资清单数组。")
    for line in lines:
        for name, minimum, quantity in fields:
            integer(line, name, quantity=quantity, minimum=minimum)
    return lines


def _reason(body):
    reason = body.get("reasonText", "")
    if not isinstance(reason, str) or len(reason) > REASON_LIMIT:
        raise AppError("VALIDATION_ERROR", f"reasonText 须为不超过 {REASON_LIMIT} 字符的字符串。")
    return reason


def _mutable(user):
    if user.role == "REPORTER":
        raise AppError("NO_PERMISSION", "申请查看人不能领用或退回物资。")
    return user


@router.get('')
def list_orders(request: Request, mine: bool = False, warehouseId: int | None = Query(None, gt=0),
                status: str | None = None, x_user: str | None = Header(None)):
    if status is not None and status not in STATUSES:
        raise AppError("QUERY_ARGUMENT_INVALID", "status 无效。")
    with request.app.state.database.sessions() as session:
        user = authenticate(session, x_user)
    return list_kits(request.app.state.database, user, mine=mine, warehouse_id=warehouseId, status=status)


@router.post('')
def create_order(request: Request, body: Any = Body(None), x_user: str | None = Header(None)):
    with request.app.state.database.sessions() as session:
        user = _mutable(authenticate(session, x_user))
    body = object_body(body)
    warehouse_id = integer(body, "warehouseId", minimum=1)
    lines = _lines(body, (("inventoryId", 1, False), ("quantity", 1, True), ("version", 0, False)))
    return create_kit(request.app.state.database, request.app.state.settings.exam_now,
                      user, warehouse_id, _reason(body), lines)


@router.get('/{order_id}')
def order_detail(order_id: int, request: Request, x_user: str | None = Header(None)):
    with request.app.state.database.sessions() as session:
        user = authenticate(session, x_user)
    return get_kit(request.app.state.database, user, order_id)


@router.post('/{order_id}/return')
def return_order(order_id: int, request: Request, body: Any = Body(None),
                 x_user: str | None = Header(None)):
    with request.app.state.database.sessions() as session:
        user = _mutable(authenticate(session, x_user))
    body = object_body(body)
    order_version = integer(body, "orderVersion")
    lines = _lines(body, (("inventoryId", 1, False), ("inventoryVersion", 0, False)))
    return return_kit(request.app.state.database, request.app.state.settings.exam_now,
                      user, order_id, order_version, lines)
