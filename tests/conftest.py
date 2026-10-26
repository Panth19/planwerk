import json
import os
from pathlib import Path

# Tests never write an audit file into the working tree.
os.environ.setdefault("PLANWERK_AUDIT_FILE", "0")

import pytest

from planwerk.model import Case

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sample_case() -> Case:
    return Case.from_json(json.loads((ROOT / "data" / "sample_case.json").read_text(encoding="utf-8")))
