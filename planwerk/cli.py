"""Command line.

    planwerk calc   [CASE] [--set factor=0.8 --set cap_amount=180000] [--json]
    planwerk fit    [CASE] --budget 6500000
    planwerk export [CASE] -o out/Anlage1.xlsx
    planwerk ask    "Was kostet ein Höchstbetrag von 180.000 €?" [--case CASE]
    planwerk memo   --scenario A= --scenario B=factor=0.6,cap_amount=120000 [--case CASE]
    planwerk serve  [--port 8765]

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
from .paths import sample_path


def _load(path: str | None) -> Case:
    p = Path(path) if path else sample_path()
    if not p.exists():
        raise ValueError(f"Datei nicht gefunden: {p}")
    if p.suffix.lower() == ".json":
        return Case.from_json(json.loads(p.read_text(encoding="utf-8")))
    return case_from_file(p)


def _value(v: str) -> Any:
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def _parse_sets(pairs: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pair in pairs:
        k, sep, v = pair.partition("=")
        if not sep or not k:
            raise ValueError(f"--set erwartet FELD=WERT, nicht {pair!r}")
        out[k.strip()] = _value(v.strip())
    return out


def _parse_scenarios(items: list[str]) -> dict[str, dict[str, Any]]:
    """'B=factor=0.6,cap_amount=120000' -> {'B': {'factor': 0.6, 'cap_amount': 120000}}"""
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        name, _, rest = item.partition("=")
        out[name] = _parse_sets([p for p in rest.split(",") if p]) if rest else {}
    return out


def eur(x: float) -> str:
    return f"{x:,.0f} €".replace(",", ".")


def _print_summary(case: Case) -> None:
    r = calculate(case.employees, case.scheme)
    sm = r.summary
    lim = sm["limits"]
    rows = [
        ("Berechtigt", f"{sm['eligible']} von {sm['headcount']}"),
        ("Summe", eur(r.total)),
        *([("Kürzungsquote", f"{r.quota:.4%}".replace(".", ","))] if r.quota < 1 else []),
        ("Median", eur(sm["median"])),
        ("Spanne", f"{eur(sm['min'])} bis {eur(sm['max'])}"),
        ("Monatsgehälter im Schnitt", f"{sm['months_equivalent']:.2f}".replace(".", ",")),
        ("Sockel / Deckel / rentennah", f"{lim['floor']} / {lim['cap']} / {lim['retirement']}"),
        *([("Abstand zum Volumen", eur(sm["budget_delta"]))] if sm["budget_delta"] is not None else []),
    ]
    width = max(len(k) for k, _ in rows)
    print(case.title, end="\n\n")
    for k, v in rows:
        print(f"  {k:<{width}}  {v}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="planwerk", description="Sozialplan-Rechner")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser, positional_case: bool = True) -> None:
        if positional_case:
            p.add_argument("case", nargs="?", default=None, help="Fall (.json) oder Mitarbeiterliste (.xlsx/.csv)")
        else:
            p.add_argument("--case", default=None, help="Fall (.json) oder Mitarbeiterliste (.xlsx/.csv)")
        p.add_argument("--set", action="append", default=[], metavar="FELD=WERT", help="Parameter ändern")

    p = sub.add_parser("calc", help="Summe und Kennzahlen")
    common(p)
    p.add_argument("--json", action="store_true", help="vollständiges Ergebnis als JSON")
    p = sub.add_parser("fit", help="Faktor oder Divisor an ein Volumen anpassen")
    common(p)
    p.add_argument("--budget", type=float, required=True)
    p = sub.add_parser("export", help="Excel-Modell mit Live-Formeln schreiben")
    common(p)
    p.add_argument("-o", "--out", default="out/Sozialplan_Anlage1.xlsx")
    p = sub.add_parser("ask", help="Frage an den Assistenten")
    common(p, positional_case=False)
    p.add_argument("question")
    p = sub.add_parser("memo", help="Kurzvermerk für die Partnerin oder den Partner")
    common(p, positional_case=False)
    p.add_argument("--scenario", action="append", required=True, metavar="NAME=FELD=WERT,...")
    s = sub.add_parser("serve", help="Web-App starten")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--host", default="127.0.0.1")
    return ap


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)

    if a.cmd == "serve":
        import uvicorn

        uvicorn.run("planwerk.api:app", host=a.host, port=a.port)
        return 0

    try:
        case = _load(a.case)
        case.scheme = case.scheme.with_changes(**_parse_sets(a.set))

        if a.cmd == "calc":
            if a.json:
                json.dump(calculate(case.employees, case.scheme).to_json(), sys.stdout, ensure_ascii=False, indent=1)
                print()
            else:
                _print_summary(case)
        elif a.cmd == "fit":
            print(json.dumps(fit_budget(case.employees, case.scheme, a.budget).to_json(), ensure_ascii=False, indent=1))
        elif a.cmd == "export":
            print(export_workbook(case, a.out))
        elif a.cmd in ("ask", "memo"):
            from .assistant import Assistant

            assistant = Assistant(case)
            if a.cmd == "ask":
                print(assistant.ask(a.question).text)
            else:
                print(assistant.draft_memo(_parse_scenarios(a.scenario)))
    except (ValueError, FileNotFoundError) as exc:
        print(f"planwerk: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
