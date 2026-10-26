"""Planwerk as an MCP server.

Lets any MCP client (Claude Code, Claude Desktop, our own agent platform)
calculate Sozialplan scenarios with the real engine instead of guessing.
Same privacy rule as the assistant: tools return aggregates and Personal-Nr.,
never names, birth dates or individual salaries.

    planwerk-mcp                         # stdio, sample case
    PLANWERK_CASE=~/cases/x.json planwerk-mcp
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from . import audit
from .engine import calculate, compare as compare_schemes, fit_budget as fit
from .excel import case_from_file, export_workbook
from .model import Case
from .privacy import assert_clean, llm_view

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample_case.json"

server = MCPServer(
    name="planwerk",
    title="Planwerk Sozialplan-Rechner",
    version="0.9.0",
    instructions=(
        "Calculates German Sozialplan severance scenarios. Never compute amounts yourself: "
        "call simulate, fit_budget or compare. Results are aggregates; individual people are "
        "identified only by Personal-Nr. Calculation aid, not legal advice."
    ),
)

_state: dict[str, Case] = {}


def _case() -> Case:
    if "case" not in _state:
        load_case(os.environ.get("PLANWERK_CASE", str(SAMPLE)))
    return _state["case"]


def _clean(payload: Any) -> Any:
    assert_clean(payload, _case().employees)
    return payload


@server.tool(description="Load a case from a .json case file or a client .xlsx/.csv employee list.")
def load_case(path: str) -> dict[str, Any]:
    p = Path(path).expanduser()
    if p.suffix.lower() == ".json":
        case = Case.from_json(json.loads(p.read_text(encoding="utf-8")))
    else:
        case = case_from_file(p)
    _state["case"] = case
    audit.event("mcp.load_case", headcount=len(case.employees), synthetic=case.synthetic)
    return {"title": case.title if case.synthetic else "Mandantenfall", "headcount": len(case.employees),
            "scheme": case.scheme.to_json()}


@server.tool(description="Current scheme and result (aggregates, distribution, age groups).")
def plan_summary() -> dict[str, Any]:
    c = _case()
    return _clean({"scheme": c.scheme.to_json(), "result": llm_view(calculate(c.employees, c.scheme))})


@server.tool(description="Recalculate with changed scheme fields, e.g. {\"cap_amount\": 180000, \"factor\": 0.8}. "
                         "Does not change the stored plan.")
def simulate(changes: dict[str, Any]) -> dict[str, Any]:
    c = _case()
    s = c.scheme.with_changes(**changes)
    with audit.timed("mcp.simulate", changed=sorted(changes)):
        return _clean({"scheme": s.to_json(), "result": llm_view(calculate(c.employees, s))})


@server.tool(description="Most generous factor (or smallest divisor) that keeps the total within budget.")
def fit_budget(budget: float, changes: dict[str, Any] | None = None) -> dict[str, Any]:
    c = _case()
    with audit.timed("mcp.fit_budget"):
        return fit(c.employees, c.scheme.with_changes(**(changes or {})), budget).to_json()


@server.tool(description="Compare named scenarios side by side: {\"A\": {...changes}, \"B\": {...}}.")
def compare(scenarios: dict[str, dict[str, Any]]) -> dict[str, Any]:
    c = _case()
    res = compare_schemes(c.employees, {k: c.scheme.with_changes(**v) for k, v in scenarios.items()})
    return _clean({k: {"total": v["total"], "quota": v["quota"], "summary": v["summary"]} for k, v in res.items()})


@server.tool(description="Apply changes to the stored plan (e.g. after the parties agreed).")
def set_scheme(changes: dict[str, Any]) -> dict[str, Any]:
    c = _case()
    c.scheme = c.scheme.with_changes(**changes)
    audit.event("mcp.set_scheme", changed=sorted(changes))
    return c.scheme.to_json()


@server.tool(description="Sozialauswahl ranking by points, lowest first (Personal-Nr. and points only).")
def social_ranking(limit: int = 20) -> list[dict[str, Any]]:
    c = _case()
    lines = sorted(calculate(c.employees, c.scheme).lines, key=lambda l: (l.points, l.id))
    return _clean([{"id": l.id, "points": l.points, "age": l.age, "tenure_years": int(l.tenure_months // 12)}
                   for l in lines[:limit]])


@server.tool(description="Write the current plan as a self-calculating Excel model and return the file path.")
def export_excel(path: str = "out/planwerk.xlsx") -> str:
    c = _case()
    out = export_workbook(c, Path(path).expanduser())
    audit.event("mcp.export_excel")
    return str(out.resolve())


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
