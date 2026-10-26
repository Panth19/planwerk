"""The exported Excel model must calculate exactly what the engine calculates.

We write the workbook with formulas only (no cached values), let headless
LibreOffice recalculate it, read the results back and compare every single
amount. If this test fails, either the engine or the Excel formulas drifted.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from planwerk.engine import calculate
from planwerk.excel import export_workbook, read_amounts

SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")
pytestmark = [
    pytest.mark.libreoffice,
    pytest.mark.skipif(SOFFICE is None, reason="LibreOffice not installed"),
]

SCENARIOS = {
    "default": {},
    "pro_rata": {"budget_mode": "pro_rata"},
    "divisor": {"formula": "divisor", "divisor": 75.5},
    "months_no_limits": {"tenure_rounding": "months", "floor_amount": 0, "cap_amount": 0,
                         "retirement_age": 0},
    "full_years_round_100": {"tenure_rounding": "full_years", "rounding_step": 100, "factor": 0.613},
    "divisor_pro_rata": {"formula": "divisor", "divisor": 60, "budget_mode": "pro_rata",
                         "budget": 5_000_000},
}


def recalc(src: Path, outdir: Path) -> Path:
    subprocess.run(
        [SOFFICE, "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(outdir), str(src)],
        check=True, capture_output=True, timeout=120,
    )
    return outdir / src.name


@pytest.mark.parametrize("name", SCENARIOS)
def test_excel_matches_engine(sample_case, tmp_path, name):
    case = sample_case
    case.scheme = case.scheme.with_changes(**SCENARIOS[name])
    expected = calculate(case.employees, case.scheme)

    src = export_workbook(case, tmp_path / "in" / f"{name}.xlsx")
    amounts = read_amounts(recalc(src, tmp_path / "out"))

    mismatches = [(l.id, l.amount, amounts.get(l.id)) for l in expected.lines
                  if amounts.get(l.id) != l.amount]
    assert not mismatches, f"{len(mismatches)} rows differ, first: {mismatches[:5]}"
    assert sum(amounts.values()) == pytest.approx(expected.total, abs=0.005)
