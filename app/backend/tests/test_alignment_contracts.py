import json

from jsonschema import Draft202012Validator

from materialops.config import CONTRACTS_ROOT


def test_agent_response_allows_the_published_session_identifier():
    schema = json.loads((CONTRACTS_ROOT / "schemas" / "agent-response.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    validator.validate({"status": "OK", "answer": "已查询。", "toolTrace": [], "sessionId": "session-example"})
    assert not validator.is_valid({"status": "OK", "answer": "", "toolTrace": [], "sessionId": " "})
