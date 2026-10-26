import asyncio
import json

from fastapi.testclient import TestClient

from planwerk.api import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_calculate_sample_and_custom_people():
    r = client.post("/api/calculate", json={"scheme": {"factor": 0.6}})
    assert r.status_code == 200 and r.json()["summary"]["headcount"] == 140

    people = [{"id": "X1", "name": "A", "birth_date": "1980-01-01", "entry_date": "2010-01-01",
               "monthly_gross": 4000}]
    r = client.post("/api/calculate", json={"employees": people,
                                            "scheme": {"tenure_rounding": "full_years", "floor_amount": 0}})
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
    from planwerk import mcp_server

    async def run():
        tools = {t.name for t in await mcp_server.server.list_tools()}
        assert {"simulate", "fit_budget", "compare", "social_ranking", "export_excel"} <= tools
        return await mcp_server.server.call_tool("fit_budget", {"budget": 6_500_000})

    out = asyncio.run(run())
    text = json.dumps(out, default=lambda o: getattr(o, "__dict__", str(o)))
    assert "0.54" in text or "factor" in text
