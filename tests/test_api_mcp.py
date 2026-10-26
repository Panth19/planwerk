import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from planwerk.api import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_calculate_sample_and_custom_people():
    r = client.post("/api/calculate", json={"scheme": {"factor": 0.6}})
    assert r.status_code == 200 and r.json()["summary"]["headcount"] == 140

    people = [{"id": "X1", "name": "A", "birth_date": "1980-01-01", "entry_date": "2010-01-01", "monthly_gross": 4000}]
    r = client.post(
        "/api/calculate", json={"employees": people, "scheme": {"tenure_rounding": "full_years", "floor_amount": 0}}
    )
    assert r.json()["total"] == 16 * 4000 * 0.75


def test_bad_input_is_a_422_with_a_reason():
    r = client.post("/api/calculate", json={"scheme": {"formula": "magic"}})
    assert r.status_code == 422


def test_export_returns_xlsx():
    r = client.post("/api/export.xlsx", json={})
    assert r.status_code == 200
    assert r.content[:2] == b"PK"


def test_import_csv():
    csv = "Personalnummer;Name;Geburtsdatum;Eintritt;Brutto\n1;A B;01.01.1980;01.01.2010;4000\n"
    r = client.post("/api/import", files={"file": ("liste.csv", csv.encode(), "text/csv")})
    assert r.json()["ok"] and len(r.json()["employees"]) == 1


def test_assistant_without_key_explains_how_to_enable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("PLANWERK_LLM", raising=False)
    r = client.post("/api/ask", json={"question": "Median?"})
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_mcp_server_lists_and_runs_tools():
    pytest.importorskip("mcp")
    from planwerk import mcp_server

    async def run():
        tools = {t.name for t in await mcp_server.server.list_tools()}
        assert {"simulate", "fit_budget", "compare", "social_ranking", "export_excel"} <= tools
        return await mcp_server.server.call_tool("fit_budget", {"budget": 6_500_000})

    out = asyncio.run(run())
    text = json.dumps(out, default=lambda o: getattr(o, "__dict__", str(o)))
    assert "0.54" in text or "factor" in text


def test_security_headers():
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_web_app_and_sample_are_served():
    assert "Planwerk" in client.get("/").text
    assert client.get("/sample_case.json").json()["synthetic"] is True
    assert client.get("/engine.js").status_code == 200


def test_broken_upload_is_a_422_not_a_500():
    r = client.post("/api/import", files={"file": ("x.xlsx", b"not a zip", "application/octet-stream")})
    assert r.status_code == 422 and "nicht lesbar" in r.json()["detail"]


def test_upload_size_and_type_limits():
    big = b"a;b;c\n" * (2 * 1024 * 1024)
    assert client.post("/api/import", files={"file": ("x.csv", big, "text/csv")}).status_code == 413
    assert client.post("/api/import", files={"file": ("x.pdf", b"%PDF", "application/pdf")}).status_code == 415


def test_unknown_headers_are_mapped_by_the_model_when_available(monkeypatch):
    import planwerk.assistant as assistant_mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    seen = {}

    def fake_map(unmapped, missing, llm=None):
        seen["args"] = (sorted(unmapped), sorted(missing))
        return {"birth_date": "Geburtstag", "entry_date": "Startdatum", "monthly_gross": "Fixum"}

    monkeypatch.setattr(assistant_mod, "map_headers", fake_map)
    csv = "Kennung;Geburtstag;Startdatum;Fixum\nA;1980-01-01;2000-01-01;5000\n"
    r = client.post("/api/import", files={"file": ("liste.csv", csv.encode(), "text/csv")}).json()
    assert r["ok"] and r["mapped_by_model"]["monthly_gross"] == "Fixum"
    assert seen["args"] == (
        ["Fixum", "Geburtstag", "Kennung", "Startdatum"],
        ["birth_date", "entry_date", "monthly_gross"],
    )


def test_model_outage_is_a_502_with_a_plain_message(monkeypatch):
    import planwerk.assistant as assistant_mod

    class Down:
        def complete(self, *a, **k):
            raise ConnectionError("boom")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(assistant_mod, "default_llm", lambda: Down())
    r = client.post("/api/ask", json={"question": "Median?"})
    assert r.status_code == 502 and "nicht erreichbar" in r.json()["detail"]


def test_export_cleans_up_its_temp_folder(monkeypatch, tmp_path):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    r = client.post("/api/export.xlsx", json={})
    assert r.status_code == 200 and "Sozialplan_Anlage1_" in r.headers["content-disposition"]
    assert list(tmp_path.iterdir()) == []
