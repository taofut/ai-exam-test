"""T2 safeguard analysis: real model call, source checks and the three human decisions."""
import json
import time

from jsonschema import Draft202012Validator, ValidationError
from sqlalchemy import update

from materialops.ai.client import ModelClient, ModelError
from materialops.ai.prompts import render_prompt
from materialops.config import CONTRACTS_ROOT
from materialops.errors import AppError
from materialops.models import AICallLog, Item, Warehouse
from materialops.services import knowledge
from materialops.services.access import department_scope
from materialops.services.clock import iso, now
from materialops.services.queries import get_inventory, issue_stats

PROMPT_NAME = "replenishment-v1"
MAX_QUANTITY = 500
FAILURE_LIMIT = 200
PENDING = "PENDING"
SUGGESTION_FIELDS = ("warehouseId", "itemId", "suggestedQuantity", "reason", "confidence",
                     "needHuman", "knowledgeReferences")
SUGGESTION_VALIDATOR = Draft202012Validator(json.loads(
    (CONTRACTS_ROOT / "schemas" / "ai-replenishment.schema.json").read_text(encoding="utf-8")))


class AdviceInvalid(ValueError):
    """Model output is unusable as a safeguard suggestion for this call."""


def analyze(database, settings, user, inventory_id, fault):
    snapshot, today, as_of, departments = _evidence(database, settings, user, inventory_id)
    maintenance, generic = knowledge.applicable(departments, snapshot["itemNo"])
    documents = knowledge.context_documents(maintenance, generic)
    review_items = knowledge.gap_review_items(snapshot["itemNo"], maintenance)
    review_items += knowledge.conflict_review_items(maintenance)

    started = time.perf_counter()
    raw = failure = prompt_version = None
    suggestion, degraded, tokens = None, False, (None, None)
    try:
        rendered = _render(snapshot, today, documents)
        prompt_version = rendered.version
        result = ModelClient(settings).complete_json(
            system=rendered.system, user=rendered.user, fault=fault,
            fault_suggestion=_fault_baseline(snapshot, documents, today))
        raw, tokens = result.raw, (result.input_tokens, result.output_tokens)
        duration = result.duration_ms
        suggestion = _parse(result.raw, snapshot, documents)
    except (ModelError, ValueError) as exc:
        # Model transport, output structure and source failures degrade to a marked backup value.
        degraded, failure = True, _failure_text(exc)
        duration = int((time.perf_counter() - started) * 1000)
        suggestion = _fallback(snapshot, today)
    if degraded:
        review_items.append(f"模型结果不可用（{failure}），已按真实库存给出备用建议，须人工复核。")

    requires_review = bool(review_items)
    if requires_review:
        suggestion = {**suggestion, "needHuman": True}
    context = {"inventory": snapshot, "issueStats": today, "knowledge": documents,
               "review": {"degraded": degraded, "requiresHumanReview": requires_review,
                          "reviewItems": review_items}}
    call_id = _save(database, settings, user, snapshot, as_of, suggestion, context, {
        "raw": raw, "failure": failure, "duration": duration, "tokens": tokens,
        "prompt_version": prompt_version or PROMPT_NAME})
    with database.sessions() as session:
        return _response(session.get(AICallLog, call_id))


def read_analysis(database, user, inventory_id, call_id):
    with database.sessions() as session:
        get_inventory(session, user, inventory_id)
        log = session.get(AICallLog, call_id)
        if log is None or log.inventory_id != inventory_id:
            raise AppError("AI_CALL_NOT_FOUND", "分析记录不存在。")
        return _response(log)


def decide(database, settings, user, inventory_id, call_id, action, body):
    with database.sessions() as session:
        inventory = get_inventory(session, user, inventory_id)
        log = session.get(AICallLog, call_id)
        if log is None or log.inventory_id != inventory.id:
            raise AppError("AI_CALL_NOT_FOUND", "分析记录不存在。")
        if log.decision != PENDING:
            raise AppError("AI_DECISION_CONFLICT", "该建议已决定，不能重复决定。")
        reviewed = body.get("reviewed", False)
        if action != "reject":
            if bool((log.context or {}).get("review", {}).get("requiresHumanReview")) and reviewed is not True:
                raise AppError("HUMAN_REVIEW_REQUIRED", "该建议须先完成人工复核后才能采纳。")
            if inventory.version != log.inventory_version:
                raise AppError("VERSION_CONFLICT", "库存已变化，请重新分析后再决定。")
        decision, final = _plan(action, body, log.original_suggestion or {})
        at = now(session, settings.exam_now)
        context = {**(log.context or {}),
                   "decisionMeta": {"reviewed": reviewed if action != "reject" else None,
                                    "actorId": user.id, "at": iso(at)}}
        updated = session.execute(update(AICallLog).where(
            AICallLog.id == call_id, AICallLog.decision == PENDING).values(
            decision=decision, final_suggestion=final, context=context))
        if updated.rowcount != 1:
            session.rollback()
            raise AppError("AI_DECISION_CONFLICT", "该建议已被其他请求决定。")
        session.commit()
        session.refresh(log)
        return _response(log)


def _plan(action, body, original):
    if action == "reject":
        return "REJECTED", None
    if action == "adopt":
        return "ADOPTED", dict(original)
    final = {**original, "suggestedQuantity": body["suggestedQuantity"], "reason": body["reason"]}
    return "ADOPTED_EDITED", final


def _evidence(database, settings, user, inventory_id):
    with database.sessions() as session:
        inventory = get_inventory(session, user, inventory_id)
        item = session.get(Item, inventory.item_id)
        warehouse = session.get(Warehouse, inventory.warehouse_id)
        stats = issue_stats(session, user, settings.exam_now,
                            warehouseId=inventory.warehouse_id, itemId=inventory.item_id)
        as_of = now(session, settings.exam_now)
        departments = department_scope(session, user)
        snapshot = {"id": inventory.id, "warehouseId": warehouse.id, "warehouseName": warehouse.name,
                    "itemId": item.id, "itemNo": item.item_no, "itemName": item.name, "unit": item.unit,
                    "onHand": inventory.on_hand, "version": inventory.version,
                    "reorderPoint": item.reorder_point, "targetStock": item.target_stock}
        today = {"period": "TODAY", "quantity": stats["totalQuantity"] or 0,
                 "scope": f"仓库{inventory.warehouse_id}/物资{inventory.item_id}", "asOf": iso(as_of)}
    return snapshot, today, as_of, departments


def _render(snapshot, stats, documents):
    return render_prompt(PROMPT_NAME, {"inventory": snapshot, "issue_stats": stats,
                                       "knowledge": documents,
                                       "output_schema": SUGGESTION_VALIDATOR.schema})


def _parse(raw, snapshot, documents):
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise AdviceInvalid("模型输出不是合法 JSON") from exc
    if not isinstance(data, dict):
        raise AdviceInvalid("模型输出不是 JSON 对象")
    if data.get("warehouseId") != snapshot["warehouseId"] or data.get("itemId") != snapshot["itemId"]:
        raise AdviceInvalid("建议实体与当前库存不一致")
    if data.get("references"):
        raise AdviceInvalid("本版不检索或引用历史单据")
    knowledge.validate_references(data.get("knowledgeReferences", []), documents)
    suggestion = {field: data.get(field) for field in SUGGESTION_FIELDS}
    try:
        SUGGESTION_VALIDATOR.validate(suggestion)
    except ValidationError as exc:
        raise AdviceInvalid("建议结构或数量不符合契约") from exc
    return suggestion


def _fallback(snapshot, today):
    gap = max(0, min(MAX_QUANTITY, snapshot["targetStock"] - snapshot["onHand"]))
    return {"warehouseId": snapshot["warehouseId"], "itemId": snapshot["itemId"],
            "suggestedQuantity": gap,
            "reason": f"模型未返回可用结果，已按实时数量给出备用值：当前余额{snapshot['onHand']}"
                      f"{snapshot['unit']}、补货点{snapshot['reorderPoint']}、目标库存"
                      f"{snapshot['targetStock']}，本日领用{today['quantity']}{snapshot['unit']}；"
                      f"按目标库存与余额的差额计算，须人工核实后决定。",
            "confidence": 0, "needHuman": True, "knowledgeReferences": []}


def _fault_baseline(snapshot, documents, today):
    """Organizer fault fixtures are applied to this real-evidence baseline, then re-validated."""
    basis = _fallback(snapshot, today)
    # A non-degraded fixture must not carry the degraded wording that _fallback uses.
    basis["reason"] = (f"当前余额{snapshot['onHand']}{snapshot['unit']}、补货点{snapshot['reorderPoint']}、"
                       f"目标库存{snapshot['targetStock']}，本日领用{today['quantity']}{snapshot['unit']}；"
                       f"按目标库存与余额的差额给出待核数量，结合维护依据确定。")
    if documents:
        doc = documents[0]
        basis = {**basis, "confidence": 0.8, "needHuman": False,
                 "knowledgeReferences": [{"docId": doc["docId"], "title": doc["title"],
                                          "version": doc["version"],
                                          "quote": doc["content"][:40]}]}
    return basis


def _save(database, settings, user, snapshot, as_of, suggestion, context, meta):
    with database.sessions() as session:
        log = AICallLog(inventory_id=snapshot["id"], inventory_version=snapshot["version"],
                        actor_id=user.id, model=settings.model or "unconfigured",
                        prompt_version=meta["prompt_version"], duration_ms=meta["duration"],
                        raw_output=meta["raw"], input_tokens=meta["tokens"][0],
                        output_tokens=meta["tokens"][1], failure_reason=meta["failure"],
                        context=context, original_suggestion=suggestion, final_suggestion=None,
                        decision=PENDING, created_at=as_of)
        session.add(log)
        session.commit()
        return log.id


def _response(log):
    context = log.context or {}
    review = context.get("review", {})
    meta = context.get("decisionMeta") or {}
    return {"callId": log.id, "inventoryId": log.inventory_id,
            "inventoryVersion": log.inventory_version, "suggestion": log.original_suggestion,
            "degraded": bool(review.get("degraded")),
            "requiresHumanReview": bool(review.get("requiresHumanReview")),
            "reviewItems": review.get("reviewItems", []), "decision": log.decision,
            "context": context,
            "usage": {"inputTokens": log.input_tokens, "outputTokens": log.output_tokens,
                      "model": log.model},
            "finalSuggestion": log.final_suggestion, "reviewed": meta.get("reviewed"),
            "decisionById": meta.get("actorId"), "decisionAt": meta.get("at")}


def _failure_text(exc):
    message = str(exc).strip()[:FAILURE_LIMIT]
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__
