"""Read-only fixture validation must catch invalid knowledge before distribution."""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("verify_resources", ROOT / "scripts/verify_resources.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def resources():
    knowledge = json.loads((ROOT / "resources/demo/knowledge-baseline.json").read_text(encoding="utf-8"))
    dataset = json.loads((ROOT / "resources/demo/material-kit-dataset.json").read_text(encoding="utf-8"))
    return knowledge, dataset


def validate(knowledge, dataset):
    assert callable(getattr(verifier, "validate_knowledge", None)), "Current read-only knowledge must be validated"
    verifier.validate_knowledge(knowledge, dataset)


def test_public_knowledge_validates_without_modifying_inputs():
    knowledge, dataset = resources()
    before = copy.deepcopy((knowledge, dataset))
    validate(knowledge, dataset)
    assert (knowledge, dataset) == before


@pytest.mark.parametrize("change", [
    lambda k: k["documents"].append(copy.deepcopy(k["documents"][0])),
    lambda k: k["documents"][0].update(deptId=999999),
    lambda k: k["documents"][0].update(itemNos=["UNKNOWN-ITEM"]),
    lambda k: k["documents"][0].update(content="   "),
    lambda k: k["documents"][0].update(version=0),
    lambda k: k["documents"][0].update(status="READY"),
])
def test_invalid_knowledge_is_rejected(change):
    knowledge, dataset = resources()
    change(knowledge)
    with pytest.raises(ValueError):
        validate(knowledge, dataset)
