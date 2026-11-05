"""Validate published event examples, not candidate streaming implementation."""
import json

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from materialops.config import CONTRACTS_ROOT


def validator():
    folder = CONTRACTS_ROOT / 'schemas'
    response = json.loads((folder / 'agent-response.schema.json').read_text(encoding='utf-8'))
    schema = json.loads((folder / 'agent-stream-event.schema.json').read_text(encoding='utf-8'))
    registry = Registry().with_resource(response['$id'], Resource.from_contents(response))
    return Draft202012Validator(schema, registry=registry)


@pytest.mark.parametrize('event,data', [
    ('meta', {'sessionId': 'session-1', 'turnId': 'turn-1'}),
    ('progress', {'phase': 'model', 'message': '正在分析'}),
    ('result', {'sessionId': 'session-1', 'status': 'OK', 'answer': '已查询', 'toolTrace': []}),
    ('error', {'code': 'INTERNAL_ERROR', 'message': '请核对原操作', 'outcome': 'UNKNOWN'}),
])
def test_published_sse_events_are_valid(event, data):
    validator().validate({'id': 'turn-1:1', 'event': event, 'data': data})


@pytest.mark.parametrize('packet', [
    {'id': 'turn-1:0', 'event': 'meta', 'data': {'sessionId': 's', 'turnId': 'turn-1'}},
    {'id': 'turn-1:1', 'event': 'meta', 'data': {'sessionId': ' ', 'turnId': 'turn-1'}},
    {'id': 'turn-1:1', 'event': 'progress', 'data': {'phase': 'done', 'message': '完成'}},
    {'id': 'turn-1:1', 'event': 'result', 'data': {'sessionId': 's', 'status': 'EXECUTED', 'answer': '完成', 'toolTrace': []}},
    {'id': 'turn-1:1', 'event': 'error', 'data': {'code': 'INTERNAL_ERROR', 'message': '失败'}},
    {'id': 'turn-1:1', 'event': 'done', 'data': {}},
])
def test_invalid_frames_cannot_masquerade_as_success(packet):
    assert not validator().is_valid(packet)
