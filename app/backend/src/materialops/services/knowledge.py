"""Read-only preloaded knowledge: visibility, applicability, quotes and explicit conflicts."""
import json
import re

from materialops.config import RESOURCES_ROOT

KNOWLEDGE_FILE = RESOURCES_ROOT / "demo" / "knowledge-baseline.json"
PERIOD = re.compile(r"每(?:日|天|周|月|季度|季|年)")
REFERENCE_FIELDS = {"docId", "title", "version", "quote"}


class ReferenceInvalid(ValueError):
    """A model reference does not match the documents of this call."""


def _documents():
    return json.loads(KNOWLEDGE_FILE.read_text(encoding="utf-8"))["documents"]


def applicable(departments, item_no):
    """Split visible ACTIVE documents into item maintenance docs and generic ones."""
    maintenance, generic = [], []
    for doc in _documents():
        if doc["status"] != "ACTIVE":
            continue
        if doc["deptId"] is not None and doc["deptId"] not in departments:
            continue
        if doc["itemNos"]:
            # An item-number list is a hard limit; keywords cannot extend it.
            if item_no in doc["itemNos"]:
                maintenance.append(doc)
        else:
            generic.append(doc)
    return maintenance, generic


def context_documents(maintenance, generic):
    """The exact documents this call may cite, kept for re-reading the source text."""
    return [{"docId": doc["docId"], "title": doc["title"], "version": doc["version"],
             "general": not doc["itemNos"], "content": doc["content"]} for doc in maintenance + generic]


def gap_review_items(item_no, maintenance):
    """Generic rules never replace item maintenance evidence."""
    if maintenance:
        return []
    return [f"未检索到物资 {item_no} 适用的维护资料，仅有通用规则，补货结论须人工核实。"]


def conflict_review_items(maintenance):
    """Only an explicit mismatch of the same periodicity counts; no semantic inference."""
    dated = [(doc, PERIOD.findall(doc["content"])) for doc in maintenance]
    dated = [(doc, periods) for doc, periods in dated if periods]
    periods = {period for _, found in dated for period in found}
    if len(periods) < 2:
        return []
    titles = "、".join(f"《{doc['title']}》" for doc, _ in dated)
    return [f"{titles}对同一事项的有效表述不一致（{'、'.join(sorted(periods))}），须人工核实后再决定。"]


def validate_references(references, documents):
    """Server-side source check: same call, same version, continuous original text."""
    if not isinstance(references, list):
        raise ReferenceInvalid("知识引用须为数组")
    allowed = {doc["docId"]: doc for doc in documents}
    for reference in references:
        if not isinstance(reference, dict) or set(reference) != REFERENCE_FIELDS:
            raise ReferenceInvalid("引用字段须为 docId/title/version/quote")
        doc = allowed.get(reference["docId"])
        if doc is None:
            raise ReferenceInvalid("引用了本次未提供的知识")
        if reference["title"] != doc["title"] or reference["version"] != doc["version"]:
            raise ReferenceInvalid("引用标题或版本与本次知识不一致")
        quote = reference["quote"]
        if not isinstance(quote, str) or not quote.strip() or quote not in doc["content"]:
            raise ReferenceInvalid("引用摘录不是本次知识正文的连续原文")
    return references
