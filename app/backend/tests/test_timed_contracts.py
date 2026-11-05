"""The minimal timed-exam payloads must work without removed business fields."""
import json
from copy import deepcopy

from jsonschema import Draft202012Validator

from materialops.config import CONTRACTS_ROOT


def schema(name):
    return Draft202012Validator(json.loads((CONTRACTS_ROOT / 'schemas' / name).read_text(encoding='utf-8')))


def suggestion():
    return {'warehouseId': 4101, 'itemId': 5101, 'suggestedQuantity': 0,
            'reason': '本次无需补充。', 'confidence': 0.8, 'needHuman': False,
            'knowledgeReferences': []}


def test_knowledge_suggestion_needs_no_historical_issue_references():
    schema('ai-replenishment.schema.json').validate(suggestion())


def test_zero_plan_and_decision_fit_in_analysis_response_without_draft():
    original = {**suggestion(), 'suggestedQuantity': 4}
    response = {'callId': 1, 'inventoryId': 8101, 'inventoryVersion': 0,
                'suggestion': original, 'degraded': False, 'requiresHumanReview': False,
                'reviewItems': [], 'decision': 'ADOPTED_EDITED', 'finalSuggestion': suggestion(),
                'reviewed': True, 'decisionById': 7102, 'decisionAt': '2026-10-12T02:00:00Z',
                'context': {'inventory': {}, 'knowledge': [],
                            'issueStats': {'period': 'TODAY', 'quantity': 0,
                                           'scope': '仓库4101/物资5101', 'asOf': '2026-10-12T02:00:00Z'}}}
    validator = schema('advice-response.schema.json')
    validator.validate(response)
    stale = deepcopy(response)
    stale['context']['issueStats']['period'] = 'THIS_WEEK'
    assert not validator.is_valid(stale)


def test_agent_minimum_result_does_not_require_tool_orchestration_trace():
    schema('agent-response.schema.json').validate({'status': 'OK', 'answer': '当前库存10个。', 'sessionId': 's-1'})
