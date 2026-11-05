"""OpenAI-compatible model HTTP boundary; business validation belongs to callers."""

import json
import time
from dataclasses import dataclass

import httpx

from materialops.ai.faults import PUBLIC_FAULTS, content_fault_payload
from materialops.config import Settings, settings as default_settings


class ModelError(Exception):
    """The model transport or response envelope failed."""


class ModelTimeout(ModelError):
    """The model request or its gateway timed out."""


@dataclass(frozen=True)
class ModelResult:
    raw: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int


@dataclass(frozen=True)
class ModelToolsResult:
    """One assistant response; arguments remain untrusted strings for callers."""

    content: str | None
    tool_calls: list[dict[str, object]]
    raw: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int


class ModelClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings if settings is not None else default_settings

    def complete_json(
        self, *, system: str, user: str, fault: str | None = None,
        fault_suggestion: dict[str, object] | None = None,
    ) -> ModelResult:
        """fault_suggestion is organizer test input, used only for local content faults."""
        started = time.perf_counter()
        if fault is not None and (not isinstance(fault, str) or fault not in PUBLIC_FAULTS):
            raise ModelError("Unknown model fault")

        if fault is not None and not self.settings.model_fault_transport:
            if fault == "timeout":
                raise ModelTimeout("Injected model timeout")
            if fault == "network":
                raise ModelError("Injected model gateway error")
            raw = "{truncated" if fault == "invalid_json" else json.dumps(
                content_fault_payload(fault, fault_suggestion),
                ensure_ascii=False,
            )
            return ModelResult(raw, None, None, self._elapsed_ms(started))

        response = self._post({
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }, fault=fault)
        try:
            message, usage = self._message_and_usage(response)
            raw = message["content"]
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("Invalid completion content")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelError("Model returned an invalid response") from exc

        return ModelResult(
            raw=raw,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            duration_ms=self._elapsed_ms(started),
        )

    def complete_tools(
        self, *, messages: list[dict[str, object]], tools: list[dict[str, object]],
        tool_choice: str | dict[str, object] = "auto",
    ) -> ModelToolsResult:
        """Send one tools request without selecting, validating or executing a tool."""
        started = time.perf_counter()
        response = self._post({
            "messages": messages, "tools": tools, "tool_choice": tool_choice,
        })
        try:
            message, usage = self._message_and_usage(response)
            content = message.get("content")
            if content is not None and not isinstance(content, str):
                raise ValueError("Invalid assistant content")
            tool_calls = message.get("tool_calls")
            if tool_calls is None:
                tool_calls = []
            if not isinstance(tool_calls, list):
                raise ValueError("Tool calls must be an array")
            for call in tool_calls:
                if not isinstance(call, dict) or call.get("type") != "function":
                    raise ValueError("Invalid tool call")
                call_id = call.get("id")
                function = call.get("function")
                if not isinstance(call_id, str) or not call_id.strip() or not isinstance(function, dict):
                    raise ValueError("Invalid tool call identifier or function")
                name, arguments = function.get("name"), function.get("arguments")
                if not isinstance(name, str) or not name.strip() or not isinstance(arguments, str):
                    raise ValueError("Invalid tool function name or arguments")
            if not tool_calls and (content is None or not content.strip()):
                raise ValueError("Assistant response is empty")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelError("Model returned an invalid response") from exc

        return ModelToolsResult(
            content=content, tool_calls=tool_calls,
            raw=json.dumps(message, ensure_ascii=False),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            duration_ms=self._elapsed_ms(started),
        )

    def _post(self, payload: dict[str, object], *, fault: str | None = None) -> httpx.Response:
        if not all(value.strip() for value in (
            self.settings.base_url, self.settings.model, self.settings.api_key,
        )):
            raise ModelError("Configure BASE_URL, MODEL and API_KEY before calling the model")
        headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        if fault is not None:
            headers["X-Model-Fault"] = fault
        try:
            response = httpx.post(
                f"{self.settings.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={"model": self.settings.model, "temperature": 0, **payload},
                timeout=self.settings.model_timeout_seconds,
            )
            if response.status_code == 504:
                raise ModelTimeout("Model gateway timeout")
            response.raise_for_status()
            return response
        except httpx.TimeoutException as exc:
            raise ModelTimeout("Model request timed out") from exc
        except httpx.HTTPError as exc:
            raise ModelError("Model gateway request failed") from exc

    @staticmethod
    def _message_and_usage(response: httpx.Response) -> tuple[dict[str, object], dict[str, object]]:
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Completion envelope must be an object")
        choices = data["choices"]
        if not isinstance(choices, list) or not choices:
            raise ValueError("Completion choices must be a nonempty array")
        message = choices[0]["message"]
        usage = data.get("usage", {})
        if not isinstance(message, dict) or not isinstance(usage, dict):
            raise ValueError("Invalid completion message or usage")
        for key in ("prompt_tokens", "completion_tokens"):
            value = usage.get(key)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("Invalid token usage")
        return message, usage

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
