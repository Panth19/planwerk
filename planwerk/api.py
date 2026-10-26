"""HTTP API and static web app.

    uvicorn planwerk.api:app --port 8765

The browser computes interactively with web/engine.js (same rules, parity
tested). The server does what the browser should not: Excel export with live
formulas, file import, and the AI assistant (API keys stay on the server).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from . import __version__, audit
from .engine import calculate, fit_budget
from .excel import export_workbook, read_employees
from .model import Case, Employee, Scheme
from .paths import HOME, WEB, sample_path
from .privacy import PrivacyViolation

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_EMPLOYEES = 20_000

app = FastAPI(title="Planwerk", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
    )
    return response


def _commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=HOME, capture_output=True, text=True, timeout=2
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


COMMIT = os.environ.get("PLANWERK_COMMIT") or _commit()


def assistant_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("PLANWERK_LLM") == "local")


class CaseIn(BaseModel):
    title: str = Field("Fall", max_length=200)
    employees: list[dict[str, Any]] | None = Field(None, max_length=MAX_EMPLOYEES)  # None = sample case
    scheme: dict[str, Any] = {}


class FitIn(CaseIn):
    budget: float = Field(gt=0)


class AskIn(CaseIn):
    question: str = Field(min_length=1, max_length=1_000)


class MemoIn(CaseIn):
    scenarios: dict[str, dict[str, Any]] = Field(min_length=1, max_length=6)


def _case(body: CaseIn) -> Case:
    try:
        if body.employees is None:
            base = Case.from_json(json.loads(sample_path().read_text(encoding="utf-8")))
            employees, synthetic = base.employees, True
        else:
            employees, synthetic = [Employee.from_json(e) for e in body.employees], False
        return Case(body.title, employees, Scheme.from_json(body.scheme), synthetic)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f"Eingabe nicht lesbar: {exc}") from exc


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": __version__, "commit": COMMIT, "assistant": assistant_available()}


@app.get("/api/sample")
@app.get("/sample_case.json")
def sample() -> JSONResponse:
    return JSONResponse(json.loads(sample_path().read_text(encoding="utf-8")))


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
    folder = Path(tempfile.mkdtemp(prefix="planwerk-"))
    name = f"Sozialplan_Anlage1_{date.today():%Y-%m-%d}.xlsx"
    export_workbook(c, folder / name)
    audit.event("api.export", headcount=len(c.employees))
    return FileResponse(
        folder / name,
        filename=name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=BackgroundTask(shutil.rmtree, folder, ignore_errors=True),
    )


@app.post("/api/import")
async def api_import(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    suffix = Path(file.filename or "liste.xlsx").suffix.lower()
    if suffix not in {".xlsx", ".xlsm", ".csv", ".txt"}:
        raise HTTPException(415, "Bitte eine .xlsx- oder .csv-Datei hochladen.")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Die Datei ist größer als 10 MB.")

    mapped_by_model: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as d:  # the upload is deleted when the block ends
        p = Path(d) / f"upload{suffix}"
        p.write_bytes(data)
        try:
            rep = read_employees(p)
            if not rep.ok and assistant_available():
                from .assistant import map_headers

                mapped_by_model = map_headers(rep.unmapped_headers, rep.missing_fields)
                if mapped_by_model:
                    rep = read_employees(p, overrides=mapped_by_model)
        except Exception as exc:  # a client file can be broken in any way
            audit.event("api.import_failed", error=type(exc).__name__)
            raise HTTPException(422, f"Datei nicht lesbar: {exc}") from exc

    audit.event(
        "api.import",
        rows=len(rep.employees),
        missing=rep.missing_fields,
        unmapped=len(rep.unmapped_headers),
        mapped_by_model=sorted(mapped_by_model),
    )
    return {
        "ok": rep.ok,
        "mapping": rep.mapping,
        "mapped_by_model": mapped_by_model,
        "unmapped_headers": rep.unmapped_headers,
        "missing_fields": rep.missing_fields,
        "warnings": rep.warnings,
        "employees": [e.to_json() for e in rep.employees],
    }


def _assistant(body: CaseIn):
    from .assistant import Assistant

    if not assistant_available():
        raise HTTPException(503, "Assistent nicht konfiguriert: ANTHROPIC_API_KEY setzen oder PLANWERK_LLM=local.")
    return Assistant(_case(body))


def _model_call(fn):
    try:
        return fn()
    except PrivacyViolation as exc:
        audit.event("assistant.privacy_stop", reason=str(exc).split(" of ")[0])
        raise HTTPException(500, "Anfrage gestoppt: personenbezogene Daten im Modellaufruf erkannt.") from exc
    except HTTPException:
        raise
    except Exception as exc:  # network, rate limits, provider errors
        audit.event("assistant.model_error", error=type(exc).__name__)
        raise HTTPException(
            502, "Das Sprachmodell ist gerade nicht erreichbar. Bitte später erneut versuchen."
        ) from exc


@app.post("/api/ask")
def api_ask(body: AskIn) -> dict[str, Any]:
    assistant = _assistant(body)
    a = _model_call(lambda: assistant.ask(body.question))
    return {"answer": a.text, "blocked": a.blocked, "tools": a.tool_trace}


@app.post("/api/memo")
def api_memo(body: MemoIn) -> dict[str, Any]:
    assistant = _assistant(body)
    return {"memo": _model_call(lambda: assistant.draft_memo(body.scenarios))}


if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
