"""HTTP API and static web app.

    uvicorn planwerk.api:app --port 8765

The browser computes interactively with web/engine.js (same rules, parity
tested). The server does what the browser should not: Excel export with live
formulas, file import, and the AI assistant (API keys stay on the server).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, audit
from .engine import calculate, fit_budget
from .excel import export_workbook, read_employees
from .model import Case, Employee, Scheme

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
SAMPLE = ROOT / "data" / "sample_case.json"

app = FastAPI(title="Planwerk", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, timeout=2).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


COMMIT = os.environ.get("PLANWERK_COMMIT") or _commit()


class CaseIn(BaseModel):
    title: str = "Fall"
    employees: list[dict[str, Any]] | None = None  # None = sample case
    scheme: dict[str, Any] = {}


class FitIn(CaseIn):
    budget: float


class AskIn(CaseIn):
    question: str


class MemoIn(CaseIn):
    scenarios: dict[str, dict[str, Any]]


def _case(body: CaseIn) -> Case:
    try:
        if body.employees is None:
            base = Case.from_json(json.loads(SAMPLE.read_text(encoding="utf-8")))
            employees, synthetic = base.employees, True
        else:
            employees, synthetic = [Employee.from_json(e) for e in body.employees], False
        return Case(body.title, employees, Scheme.from_json(body.scheme), synthetic)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f"Eingabe nicht lesbar: {exc}") from exc


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": __version__, "commit": COMMIT,
            "assistant": bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("PLANWERK_LLM") == "local")}


@app.get("/api/sample")
def sample() -> JSONResponse:
    return JSONResponse(json.loads(SAMPLE.read_text(encoding="utf-8")))


@app.post("/api/calculate")
def api_calculate(body: CaseIn) -> dict[str, Any]:
    c = _case(body)
    with audit.timed("api.calculate", headcount=len(c.employees)) as info:
        r = calculate(c.employees, c.scheme)
        info.update(total=r.total, quota=round(r.quota, 6))
    return r.to_json()


@app.post("/api/fit")
def api_fit(body: FitIn) -> dict[str, Any]:
    c = _case(body)
    with audit.timed("api.fit", headcount=len(c.employees)):
        return fit_budget(c.employees, c.scheme, body.budget).to_json()


@app.post("/api/export.xlsx")
def api_export(body: CaseIn) -> FileResponse:
    c = _case(body)
    tmp = Path(tempfile.mkdtemp(prefix="planwerk-")) / "Sozialplan_Anlage1.xlsx"
    export_workbook(c, tmp)
    audit.event("api.export", headcount=len(c.employees))
    return FileResponse(tmp, filename=tmp.name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/import")
async def api_import(file: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(file.filename or "liste.xlsx").suffix.lower()
    if suffix not in {".xlsx", ".xlsm", ".csv", ".txt"}:
        raise HTTPException(415, "Bitte eine .xlsx- oder .csv-Datei hochladen.")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / f"upload{suffix}"
        p.write_bytes(await file.read())
        rep = read_employees(p)  # temp file is deleted when the block ends
    audit.event("api.import", rows=len(rep.employees), missing=rep.missing_fields, unmapped=len(rep.unmapped_headers))
    return {"ok": rep.ok, "mapping": rep.mapping, "unmapped_headers": rep.unmapped_headers,
            "missing_fields": rep.missing_fields, "warnings": rep.warnings,
            "employees": [e.to_json() for e in rep.employees]}


def _assistant(body: CaseIn):
    from .assistant import Assistant

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("PLANWERK_LLM") == "local"):
        raise HTTPException(503, "Assistent nicht konfiguriert: ANTHROPIC_API_KEY setzen oder PLANWERK_LLM=local.")
    return Assistant(_case(body))


@app.post("/api/ask")
def api_ask(body: AskIn) -> dict[str, Any]:
    a = _assistant(body).ask(body.question)
    return {"answer": a.text, "blocked": a.blocked, "tools": a.tool_trace}


@app.post("/api/memo")
def api_memo(body: MemoIn) -> dict[str, Any]:
    return {"memo": _assistant(body).draft_memo(body.scenarios)}


if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
