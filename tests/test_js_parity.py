"""The browser engine (web/engine.js) must match the Python engine exactly.

Not approximately: every line, every amount, every summary field, and the
fitted factor. Floats are compared with ==. JSON round-trips doubles exactly.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from planwerk.engine import calculate, fit_budget

NODE = shutil.which("node")
pytestmark = [pytest.mark.node, pytest.mark.skipif(NODE is None, reason="Node.js not installed")]

HERE = Path(__file__).parent
SCENARIOS = {
    "default": {},
    "pro_rata": {"budget_mode": "pro_rata"},
    "divisor": {"formula": "divisor", "divisor": 72.5},
    "months": {"tenure_rounding": "months", "cap_amount": 0, "floor_amount": 0},
    "full_years_step_10": {"tenure_rounding": "full_years", "rounding_step": 10, "factor": 1.15},
    "strict": {"min_tenure_months": 60, "retirement_age": 58, "retirement_cap_months": 8.5},
    "stichtag_leap": {"stichtag": "2028-02-29", "factor": 0.333},
}


@pytest.fixture(scope="module")
def js_results(tmp_path_factory):
    d = tmp_path_factory.mktemp("js")
    (d / "scen.json").write_text(json.dumps(SCENARIOS))
    out = subprocess.run(
        [NODE, str(HERE / "js_runner.js"), str(HERE.parent / "data" / "sample_case.json"), str(d / "scen.json")],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(out.stdout)


@pytest.mark.parametrize("name", SCENARIOS)
def test_calculation_identical(sample_case, js_results, name):
    scheme = sample_case.scheme.with_changes(**SCENARIOS[name])
    py = calculate(sample_case.employees, scheme).to_json()
    js = js_results[name]["result"]
    for a, b in zip(py["lines"], js["lines"], strict=True):
        assert a == b, f"{a['id']} differs"
    assert py["summary"] == js["summary"]
    assert (py["total"], py["quota"], py["total_gross"]) == (js["total"], js["quota"], js["total_gross"])


@pytest.mark.parametrize("name", SCENARIOS)
def test_fit_identical(sample_case, js_results, name):
    scheme = sample_case.scheme.with_changes(**SCENARIOS[name])
    py = fit_budget(sample_case.employees, scheme, 6_000_000).to_json()
    assert py == js_results[name]["fit"]
