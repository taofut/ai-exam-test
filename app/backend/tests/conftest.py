import json

import pytest

from materialops.config import RESOURCES_ROOT


@pytest.fixture
def baseline_dataset():
    """Small, explicit fixture for tests of the original query and stock helpers."""
    return json.loads((RESOURCES_ROOT / "demo/seed-data.json").read_text(encoding="utf-8"))
