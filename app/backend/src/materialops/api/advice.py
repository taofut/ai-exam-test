"""T2 routes: one analysis, three human decisions and re-reading a stored decision."""
import json
from typing import Any

from fastapi import APIRouter, Body, Header, Request
from jsonschema import Draft202012Validator, ValidationError

from materialops.api.validation import object_body
from materialops.config import CONTRACTS_ROOT
from materialops.errors import AppError
from materialops.services.access import authenticate, require_manager
from materialops.services.advice import analyze, decide, read_analysis
from materialops.services.queries import get_inventory

router = APIRouter(prefix='/api/inventories', tags=['T2 safeguard advice'])

EDIT_VALIDATOR = Draft202012Validator(json.loads(
    (CONTRACTS_ROOT / "schemas" / "advice-edit.schema.json").read_text(encoding="utf-8")))
DECISION_FIELDS = {"adopt": {"reviewed"},
                   "adopt-edited": {"suggestedQuantity", "reason", "reviewed"},
                   "reject": set()}


def _authorize(request: Request, inventory_id: int, x_user: str | None):
    """Resolve identity and the current warehouse scope before any business work."""
    with request.app.state.database.sessions() as session:
        user = authenticate(session, x_user)
        require_manager(user)
        get_inventory(session, user, inventory_id)
    return user


@router.post('/{inventory_id}/ai-replenishment')
def create_analysis(inventory_id: int, request: Request, body: Any = Body(None),
                    x_user: str | None = Header(None), x_model_fault: str | None = Header(None)):
    user = _authorize(request, inventory_id, x_user)
    if body is not None:
        object_body(body)
    return analyze(request.app.state.database, request.app.state.settings, user,
                   inventory_id, x_model_fault)


@router.post('/{inventory_id}/ai-replenishment/{call_id}/{action}')
def submit_decision(inventory_id: int, call_id: int, action: str, request: Request,
                    body: Any = Body(None), x_user: str | None = Header(None)):
    user = _authorize(request, inventory_id, x_user)
    if action not in DECISION_FIELDS:
        raise AppError("QUERY_ARGUMENT_INVALID", "不支持该建议决定。")
    offered = object_body(body, empty=True)
    if set(offered) - DECISION_FIELDS[action]:
        raise AppError("VALIDATION_ERROR", "决定只接受数量、理由和复核确认。")
    if action == "adopt":
        if type(offered.get("reviewed", False)) is not bool:
            raise AppError("VALIDATION_ERROR", "reviewed 须为布尔值。")
    elif action == "adopt-edited":
        try:
            EDIT_VALIDATOR.validate(offered)
        except ValidationError as exc:
            raise AppError("VALIDATION_ERROR", "修改后采纳须提交数量、理由和reviewed复核确认。") from exc
    return decide(request.app.state.database, request.app.state.settings, user,
                  inventory_id, call_id, action, offered)


@router.get('/{inventory_id}/ai-replenishment/{call_id}')
def analysis_result(inventory_id: int, call_id: int, request: Request,
                    x_user: str | None = Header(None)):
    user = _authorize(request, inventory_id, x_user)
    return read_analysis(request.app.state.database, user, inventory_id, call_id)
