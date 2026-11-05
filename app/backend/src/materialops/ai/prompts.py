"""Load versioned prompts and insert caller data without template object access."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from string import Formatter

from materialops.config import BACKEND_ROOT

PROMPTS_ROOT = BACKEND_ROOT / "prompts"
_PROMPT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_VARIABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class PromptError(ValueError):
    """The prompt definition or its JSON input is invalid."""


@dataclass(frozen=True)
class RenderedPrompt:
    version: str
    system: str
    user: str


def render_prompt(
    name: str, variables: dict[str, object], *, prompt_dir: Path | None = None,
) -> RenderedPrompt:
    """Render declared simple placeholders once; keep every input as JSON data.

    Only the task text receives variable data. System instructions are trusted
    prompt-file text, and callers must still authorize and validate business data.
    """
    if not isinstance(name, str) or not _PROMPT_NAME.fullmatch(name):
        raise PromptError("Invalid prompt name")
    root = prompt_dir if prompt_dir is not None else PROMPTS_ROOT
    try:
        definition = json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
        if not isinstance(definition, dict):
            raise ValueError("Prompt definition must be an object")
        for key in ("version", "system", "task"):
            if not isinstance(definition.get(key), str) or not definition[key].strip():
                raise ValueError("Prompt text must be nonempty")
        declared = definition["variables"]
        if not isinstance(declared, list) or any(
            not isinstance(key, str) or not _VARIABLE_NAME.fullmatch(key) for key in declared
        ) or len(set(declared)) != len(declared):
            raise ValueError("Invalid declared variables")
        if not isinstance(definition["example"], dict):
            raise ValueError("Prompt example must be an object")
        if not isinstance(variables, dict) or set(variables) != set(declared):
            raise ValueError("Input variables must match the prompt definition")
        values = {
            key: json.dumps(value, ensure_ascii=False, allow_nan=False)
            for key, value in variables.items()
        }
        fragments = []
        for literal, field, spec, conversion in Formatter().parse(definition["task"]):
            fragments.append(literal)
            if field is None:
                continue
            if field not in values or not _VARIABLE_NAME.fullmatch(field) or spec or conversion:
                raise ValueError("Only declared simple placeholders are allowed")
            fragments.append(values[field])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PromptError("Invalid prompt definition or JSON input") from exc
    return RenderedPrompt(definition["version"], definition["system"], "".join(fragments))
