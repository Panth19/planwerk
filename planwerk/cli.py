"""Command line.

    planwerk calc  [CASE] [--set factor=0.8 --set cap_amount=180000]
    planwerk fit   [CASE] --budget 6500000
    planwerk export [CASE] -o Anlage1.xlsx
    planwerk ask   [CASE] "Was kostet ein Deckel von 180.000 €?"
    planwerk serve [--port 8765]

CASE is a case .json or a client .xlsx/.csv list; default is the sample case.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .engine import calculate, fit_budget
from .excel import case_from_file, export_workbook
from .model import Case

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample_case.json"


def _load(path: str | None) -> Case:
    p = Path(path) if path else SAMPLE
    if p.suffix.lower() == ".json":
        return Case.from_json(json.loads(p.read_text(encoding="utf-8")))
    return case_from_file(p)


def _parse_sets(pairs: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pair in pairs:
        k, _, v = pair.partition("=")
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def eur(x: float) -> str:
    return f"{x:,.0f} €".replace(",", ".")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="planwerk", description="Sozialplan-Rechner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("calc", "fit", "export", "ask"):
        p = sub.add_parser(name)
        if name == "ask":
            p.add_argument("--case", default=None)
        else:
            p.add_argument("case", nargs="?", default=None)
        p.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE")
        if name == "fit":
            p.add_argument("--budget", type=float, required=True)
        if name == "export":
            p.add_argument("-o", "--out", default="out/Sozialplan_Anlage1.xlsx")
        if name == "calc":
            p.add_argument("--json", action="store_true")
        if name == "ask":
            p.add_argument("question")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args(argv)

    if a.cmd == "serve":
        import uvicorn

        uvicorn.run("planwerk.api:app", host=a.host, port=a.port)
        return 0

    case = _load(a.case)
    case.scheme = case.scheme.with_changes(**_parse_sets(a.set))

    if a.cmd == "calc":
        r = calculate(case.employees, case.scheme)
        if a.json:
            json.dump(r.to_json(), sys.stdout, ensure_ascii=False, indent=1)
            return 0
        sm = r.summary
        print(f"{case.title}\n")
        print(f"  Berechtigt        {sm['eligible']} von {sm['headcount']}")
        print(f"  Summe             {eur(r.total)}")
        if r.quota < 1:
            print(f"  Kürzungsquote     {r.quota:.4%}")
        print(f"  Median            {eur(sm['median'])}")
        print(f"  Spanne            {eur(sm['min'])} – {eur(sm['max'])}")
        print(f"  Monatsgehälter    {sm['months_equivalent']:.2f} im Schnitt")
        lim = sm["limits"]
        print(f"  Sockel/Deckel/Rente  {lim['floor']}/{lim['cap']}/{lim['retirement']}")
        if sm["budget_delta"] is not None:
            print(f"  Abstand Volumen   {eur(sm['budget_delta'])}")
    elif a.cmd == "fit":
        f = fit_budget(case.employees, case.scheme, a.budget)
        print(json.dumps(f.to_json(), ensure_ascii=False, indent=1))
    elif a.cmd == "export":
        print(export_workbook(case, a.out))
    elif a.cmd == "ask":
        from .assistant import Assistant

        print(Assistant(case).ask(a.question).text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
