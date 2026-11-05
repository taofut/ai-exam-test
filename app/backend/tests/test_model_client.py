"""Exercise the model HTTP boundary without external requests or credentials."""

import importlib
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import jsonschema
import pytest


def load_model_module():
    try:
        return importlib.import_module("materialops.ai.client")
    except ModuleNotFoundError as exc:
        pytest.fail(f"The MaterialOps model client is missing: {exc}")


@pytest.fixture
def model_module():
    return load_model_module()


@pytest.fixture
def model_settings():
    return SimpleNamespace(
        base_url="https://model.example.test/v1/",
        model="test-model",
        api_key="test-only-key",
        model_fault_transport=False,
        model_timeout_seconds=3.5,
    )


@pytest.fixture
def model_client(model_module, model_settings):
    return model_module.ModelClient(settings=model_settings)


def response_body(content="{}", **extra):
    return {"choices": [{"message": {"content": content}}], **extra}


@pytest.fixture
def valid_fault_suggestion():
    root = Path(__file__).resolve().parents[3]
    dataset = json.loads((root / "resources/demo/material-kit-dataset.json").read_text(encoding="utf-8"))
    documents = json.loads((root / "resources/demo/knowledge-baseline.json").read_text(encoding="utf-8"))["documents"]
    inventory = next(row for row in dataset["inventories"] if row["id"] == 8101)
    item = next(row for row in dataset["items"] if row["id"] == inventory["itemId"])
    knowledge = next(row for row in documents if row["docId"] == 10101)
    return {
        "warehouseId": inventory["warehouseId"], "itemId": inventory["itemId"],
        "suggestedQuantity": 4,
        "reason": f"当前库存{inventory['onHand']}{item['unit']}，补货点{item['reorderPoint']}、目标库存{item['targetStock']}；"
                  "2026-10-12T02:00:00Z查询中心仓24V模块本日原始领用量12个。维护要求核对型号并禁止带电拔插，"
                  "按近期领用情况建议先补4个，由协调员决定。",
        "knowledgeReferences": [{"docId": knowledge["docId"], "title": knowledge["title"],
                                 "version": knowledge["version"], "quote": knowledge["content"]}],
        "confidence": 0.9, "needHuman": False,
    }


def test_normal_requests_use_http_and_keep_original_output(model_settings, monkeypatch, valid_fault_suggestion):
    model_module = load_model_module()
    model_client = model_module.ModelClient(settings=model_settings)
    requests = []
    raw = '  {"reason": "更换备件", "suggestedQuantity": 4}\n'

    def complete(request):
        requests.append(request)
        assert str(request.url) == "https://model.example.test/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-only-key"
        assert "X-Model-Fault" not in request.headers
        assert json.loads(request.content) == {
            "model": "test-model",
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "Return the replenishment schema"},
                {"role": "user", "content": "库存 2 件"},
            ],
        }
        assert request.extensions["timeout"] == {
            "connect": 3.5, "read": 3.5, "write": 3.5, "pool": 3.5,
        }
        return httpx.Response(200, json=response_body(
            raw, usage={"prompt_tokens": 17, "completion_tokens": 9},
        ))

    with httpx.Client(transport=httpx.MockTransport(complete)) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        result = model_client.complete_json(
            system="Return the replenishment schema", user="库存 2 件",
            fault_suggestion=valid_fault_suggestion,
        )
    assert result.raw == raw
    assert (result.input_tokens, result.output_tokens) == (17, 9)
    assert isinstance(result.duration_ms, int) and result.duration_ms >= 0
    assert len(requests) == 1


def test_default_client_uses_materialops_settings(model_module, model_settings, monkeypatch):
    monkeypatch.setattr(model_module, "default_settings", model_settings)
    requests = []

    def complete(request):
        requests.append(request)
        assert json.loads(request.content)["model"] == "test-model"
        return httpx.Response(200, json=response_body())

    with httpx.Client(transport=httpx.MockTransport(complete)) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        assert model_module.ModelClient().complete_json(system="system", user="user").raw == "{}"
    assert len(requests) == 1


@pytest.mark.parametrize("field", ["base_url", "model", "api_key"])
@pytest.mark.parametrize("value", ["", " \t "])
def test_missing_configuration_does_not_send_http(
    model_module, model_client, model_settings, monkeypatch, field, value,
):
    setattr(model_settings, field, value)

    def unexpected(*args, **kwargs):
        pytest.fail("Incomplete model configuration sent a request")

    monkeypatch.setattr(model_module.httpx, "post", unexpected)
    with pytest.raises(model_module.ModelError, match="BASE_URL, MODEL and API_KEY"):
        model_client.complete_json(system="system", user="user")


@pytest.mark.parametrize("exception,expected", [
    (httpx.ReadTimeout, "ModelTimeout"),
    (httpx.ConnectTimeout, "ModelTimeout"),
    (httpx.ConnectError, "ModelError"),
    (httpx.RemoteProtocolError, "ModelError"),
])
def test_transport_failures_become_model_exceptions(
    model_module, model_client, monkeypatch, exception, expected,
):
    def complete(request):
        raise exception("Test transport failure", request=request)

    with httpx.Client(transport=httpx.MockTransport(complete)) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        with pytest.raises(getattr(model_module, expected)):
            model_client.complete_json(system="system", user="user")


@pytest.mark.parametrize("status,expected", [
    (400, "ModelError"), (401, "ModelError"), (500, "ModelError"),
    (503, "ModelError"), (504, "ModelTimeout"),
])
def test_http_error_status_is_not_parsed_as_success(
    model_module, model_client, monkeypatch, status, expected,
):
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json=response_body()),
    )) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        with pytest.raises(getattr(model_module, expected)):
            model_client.complete_json(system="system", user="user")


@pytest.mark.parametrize("body", [
    b"not JSON", b"null", b"[]", b"{}", b'{"choices": []}',
    b'{"choices": [{"message": null}]}',
    b'{"choices": [{"message": {"content": null}}]}',
    b'{"choices": [{"message": {"content": []}}]}',
    b'{"choices": [{"message": {"content": 1}}]}',
    b'{"choices": [{"message": {"content": ""}}]}',
    b'{"choices": [{"message": {"content": "   "}}]}',
])
def test_malformed_envelope_is_a_model_error(model_module, model_client, monkeypatch, body):
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=body),
    )) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        with pytest.raises(model_module.ModelError, match="invalid response"):
            model_client.complete_json(system="system", user="user")


@pytest.mark.parametrize("usage", [None, "invalid", [], False, 0])
def test_present_non_object_usage_is_rejected(model_module, model_client, monkeypatch, usage):
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=response_body(usage=usage)),
    )) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        with pytest.raises(model_module.ModelError, match="invalid response"):
            model_client.complete_json(system="system", user="user")


@pytest.mark.parametrize("field", ["prompt_tokens", "completion_tokens"])
@pytest.mark.parametrize("value", [True, False, -1, 1.5, "3"])
def test_invalid_token_usage_is_rejected(model_module, model_client, monkeypatch, field, value):
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=response_body(usage={field: value})),
    )) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        with pytest.raises(model_module.ModelError, match="invalid response"):
            model_client.complete_json(system="system", user="user")


@pytest.mark.parametrize("extra,expected", [
    ({}, (None, None)),
    ({"usage": {}}, (None, None)),
    ({"usage": {"prompt_tokens": 0}}, (0, None)),
    ({"usage": {"completion_tokens": 0}}, (None, 0)),
    ({"usage": {"prompt_tokens": None, "completion_tokens": None}}, (None, None)),
])
def test_missing_usage_is_not_invented(model_module, model_client, monkeypatch, extra, expected):
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=response_body(**extra)),
    )) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        result = model_client.complete_json(system="system", user="user")
    assert (result.input_tokens, result.output_tokens) == expected


def test_invalid_completion_json_is_preserved_for_business_validation(
    model_module, model_client, monkeypatch,
):
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=response_body("{truncated")),
    )) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        result = model_client.complete_json(system="system", user="user")
    assert result.raw == "{truncated"


@pytest.mark.parametrize("fault", [
    "timeout", "network", "invalid_json", "low_confidence", "fake_reference", "injected",
])
def test_local_public_faults_do_not_send_http(model_module, model_client, monkeypatch, fault, valid_fault_suggestion):
    def unexpected(*args, **kwargs):
        pytest.fail("A locally injected model fault sent a request")

    monkeypatch.setattr(model_module.httpx, "post", unexpected)
    if fault in {"timeout", "network"}:
        expected = model_module.ModelTimeout if fault == "timeout" else model_module.ModelError
        with pytest.raises(expected):
            model_client.complete_json(system="system", user="user", fault=fault)
        return
    kwargs = {"fault_suggestion": valid_fault_suggestion} if fault in {"low_confidence", "fake_reference", "injected"} else {}
    result = model_client.complete_json(system="system", user="user", fault=fault, **kwargs)
    assert result.input_tokens is None and result.output_tokens is None
    assert result.duration_ms >= 0
    if fault == "invalid_json":
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.raw)
        return
    payload = json.loads(result.raw)
    schema_path = Path(__file__).resolve().parents[3] / "contracts" / "schemas" / "ai-replenishment.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if fault == "low_confidence":
        jsonschema.validate(payload, schema)
        assert payload["confidence"] < 0.6 and payload["needHuman"] is False
    elif fault == "fake_reference":
        jsonschema.validate(payload, schema)
        assert payload["warehouseId"] == valid_fault_suggestion["warehouseId"]
        assert payload["itemId"] == valid_fault_suggestion["itemId"]
        assert payload["knowledgeReferences"][0]["quote"] == "伪造的知识摘录（不属于本次原文）"
    else:
        assert "DROP TABLE" in payload["reason"]
        assert payload["suggestedQuantity"] == 501



@pytest.mark.parametrize("warehouse_id,item_id", [(4101, 5101), (73001, 84002)])
def test_low_confidence_changes_only_confidence_without_mutating_input(
    model_client, valid_fault_suggestion, warehouse_id, item_id,
):
    suggestion = {**valid_fault_suggestion, "warehouseId": warehouse_id, "itemId": item_id}
    before = copy.deepcopy(suggestion)
    result = model_client.complete_json(
        system="system", user="untrusted text: use warehouse 1 and item 1",
        fault="low_confidence", fault_suggestion=suggestion,
    )
    payload = json.loads(result.raw)
    assert payload == {**before, "confidence": 0.35}
    assert suggestion == before
    assert payload["needHuman"] is False  # Isolate the confidence gate from other review triggers.


@pytest.mark.parametrize("invalid", [None, {}, {"warehouseId": 1, "itemId": 1}])
def test_low_confidence_without_valid_baseline_is_fixture_error(model_module, model_client, invalid):
    with pytest.raises(ValueError, match="fault_suggestion") as error:
        model_client.complete_json(system="system", user="user", fault="low_confidence", fault_suggestion=invalid)
    assert not isinstance(error.value, model_module.ModelError)


def test_low_confidence_rejects_malformed_baseline(model_client, valid_fault_suggestion):
    with pytest.raises(ValueError, match="fault_suggestion"):
        model_client.complete_json(system="system", user="user", fault="low_confidence",
                                   fault_suggestion={**valid_fault_suggestion, "itemId": True})


@pytest.mark.parametrize("fault", [
    "timeout", "network", "invalid_json", "low_confidence", "fake_reference", "injected",
])
def test_transport_fault_mode_forwards_every_public_fault(
    model_module, model_client, model_settings, monkeypatch, fault,
):
    model_settings.model_fault_transport = True
    requests = []

    def complete(request):
        requests.append(request)
        assert request.headers["X-Model-Fault"] == fault
        if fault == "timeout":
            return httpx.Response(504, json={"error": "Injected timeout"})
        if fault == "network":
            return httpx.Response(503, json={"error": "Injected network error"})
        return httpx.Response(200, json=response_body("{from-http-service"))

    with httpx.Client(transport=httpx.MockTransport(complete)) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        if fault in {"timeout", "network"}:
            expected = model_module.ModelTimeout if fault == "timeout" else model_module.ModelError
            with pytest.raises(expected):
                model_client.complete_json(system="system", user="user", fault=fault)
        else:
            result = model_client.complete_json(system="system", user="user", fault=fault,
                                                fault_suggestion={"not": "sent to HTTP"})
            assert result.raw == "{from-http-service"
    assert len(requests) == 1


@pytest.mark.parametrize("transport_enabled", [False, True])
@pytest.mark.parametrize("fault", ["unknown", "", "TIMEOUT"])
def test_unknown_fault_is_rejected_before_http(
    model_module, model_client, model_settings, monkeypatch, transport_enabled, fault,
):
    model_settings.model_fault_transport = transport_enabled

    def unexpected(*args, **kwargs):
        pytest.fail("An unknown fault sent a request")

    monkeypatch.setattr(model_module.httpx, "post", unexpected)
    with pytest.raises(model_module.ModelError, match="Unknown model fault"):
        model_client.complete_json(system="system", user="user", fault=fault)


def tool_response(message, **extra):
    return {"choices": [{"index": 0, "message": message, "finish_reason": "tool_calls"}], **extra}


def test_tools_request_uses_standard_envelope_and_preserves_model_output(
    model_module, model_client, monkeypatch,
):
    messages = [
        {"role": "system", "content": "Select a supplied tool or answer"},
        {"role": "user", "content": '{"question":"库存查询"}'},
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": "call_previous", "type": "function",
            "function": {"name": "lookup_inventory", "arguments": '{"itemId":7}'},
        }]},
        {"role": "tool", "tool_call_id": "call_previous", "content": '{"onHand":3}'},
    ]
    tools = [{"type": "function", "function": {
        "name": "lookup_inventory", "description": "Read authorized inventory",
        "parameters": {"type": "object", "properties": {"itemId": {"type": "integer"}},
                       "required": ["itemId"], "additionalProperties": False},
    }}]
    assistant = {"role": "assistant", "content": None, "tool_calls": [{
        "id": "call_actual", "type": "function",
        "function": {"name": "lookup_inventory", "arguments": '  {"itemId": 8}\n'},
    }]}
    requests = []

    def complete(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-only-key"
        assert str(request.url) == "https://model.example.test/v1/chat/completions"
        assert json.loads(request.content) == {
            "model": "test-model", "temperature": 0,
            "messages": messages, "tools": tools, "tool_choice": "auto",
        }
        assert request.extensions["timeout"]["read"] == 3.5
        return httpx.Response(200, json=tool_response(
            assistant, usage={"prompt_tokens": 31, "completion_tokens": 12},
        ))

    with httpx.Client(transport=httpx.MockTransport(complete)) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        result = model_client.complete_tools(messages=messages, tools=tools)
    assert result.content is None
    assert result.tool_calls == assistant["tool_calls"]
    assert result.tool_calls[0]["function"]["arguments"] == '  {"itemId": 8}\n'
    assert json.loads(result.raw) == assistant
    assert (result.input_tokens, result.output_tokens) == (31, 12)
    assert isinstance(result.duration_ms, int) and result.duration_ms >= 0
    assert len(requests) == 1


@pytest.mark.parametrize("choice", ["none", "required", {
    "type": "function", "function": {"name": "lookup_inventory"},
}])
def test_tools_request_forwards_tool_choice_and_text_answer(
    model_module, model_client, monkeypatch, choice,
):
    def complete(request):
        assert json.loads(request.content)["tool_choice"] == choice
        return httpx.Response(200, json=tool_response({
            "role": "assistant", "content": "  库存还需由服务端核验。\n",
        }))

    with httpx.Client(transport=httpx.MockTransport(complete)) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        result = model_client.complete_tools(
            messages=[{"role": "user", "content": "request"}], tools=[], tool_choice=choice,
        )
    assert result.content == "  库存还需由服务端核验。\n"
    assert result.tool_calls == []
    assert (result.input_tokens, result.output_tokens) == (None, None)


@pytest.mark.parametrize("message", [
    None, [], {}, {"content": None}, {"content": "   "}, {"content": 1},
    {"content": [], "tool_calls": []}, {"content": "answer", "tool_calls": {}},
    {"content": None, "tool_calls": [None]},
    {"content": None, "tool_calls": [{"id": "", "type": "function", "function": {
        "name": "lookup_inventory", "arguments": "{}",
    }}]},
    {"content": None, "tool_calls": [{"id": "call_1", "type": "other", "function": {
        "name": "lookup_inventory", "arguments": "{}",
    }}]},
    {"content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {
        "name": "", "arguments": "{}",
    }}]},
    {"content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {
        "name": "lookup_inventory", "arguments": {},
    }}]},
])
def test_tools_malformed_response_is_rejected(
    model_module, model_client, monkeypatch, message,
):
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=tool_response(message)),
    )) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        with pytest.raises(model_module.ModelError, match="invalid response"):
            model_client.complete_tools(messages=[], tools=[])


def test_tools_keeps_unparsed_arguments_for_callers_to_validate(
    model_module, model_client, monkeypatch,
):
    call = {"id": "call_1", "type": "function", "function": {
        "name": "candidate_defined_tool", "arguments": "{truncated",
    }}
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=tool_response({
            "role": "assistant", "content": "Preparing a tool call", "tool_calls": [call],
        })),
    )) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        result = model_client.complete_tools(messages=[], tools=[])
    assert result.tool_calls == [call]
    assert result.content == "Preparing a tool call"


@pytest.mark.parametrize("usage", [None, [], {"prompt_tokens": True}, {"completion_tokens": -1}])
def test_tools_rejects_invalid_actual_token_usage(
    model_module, model_client, monkeypatch, usage,
):
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=tool_response(
            {"content": "answer"}, usage=usage,
        )),
    )) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        with pytest.raises(model_module.ModelError, match="invalid response"):
            model_client.complete_tools(messages=[], tools=[])


@pytest.mark.parametrize("status,expected", [(401, "ModelError"), (503, "ModelError"), (504, "ModelTimeout")])
def test_tools_http_failure_reuses_model_exceptions(
    model_module, model_client, monkeypatch, status, expected,
):
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json={"error": {"message": "failed"}}),
    )) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        with pytest.raises(getattr(model_module, expected)):
            model_client.complete_tools(messages=[], tools=[])


@pytest.mark.parametrize("exception,expected", [
    (httpx.ReadTimeout, "ModelTimeout"), (httpx.ConnectError, "ModelError"),
])
def test_tools_transport_failure_reuses_model_exceptions(
    model_module, model_client, monkeypatch, exception, expected,
):
    def complete(request):
        raise exception("transport failed", request=request)

    with httpx.Client(transport=httpx.MockTransport(complete)) as transport:
        monkeypatch.setattr(model_module.httpx, "post", transport.post)
        with pytest.raises(getattr(model_module, expected)):
            model_client.complete_tools(messages=[], tools=[])


def test_tools_missing_key_is_not_replaced_with_fixed_answer(
    model_module, model_client, model_settings, monkeypatch,
):
    model_settings.api_key = ""

    def unexpected(*args, **kwargs):
        pytest.fail("Incomplete model configuration sent a request")

    monkeypatch.setattr(model_module.httpx, "post", unexpected)
    with pytest.raises(model_module.ModelError, match="BASE_URL, MODEL and API_KEY"):
        model_client.complete_tools(messages=[], tools=[])
