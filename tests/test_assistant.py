"""The assistant loop, with a scripted fake model (no network, no key)."""

import json

import pytest

from planwerk.assistant import Assistant, map_headers
from planwerk.engine import calculate
from planwerk.privacy import PrivacyViolation


class ScriptedLLM:
    """Plays back a list of turns; records what it was sent."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.seen = []

    def complete(self, r, system, messages, tools):
        self.seen.append({"model": r.model, "messages": json.loads(json.dumps(messages, default=str))})
        text, calls = self.turns.pop(0)
        raw = [{"type": "text", "text": text}] + [
            {"type": "tool_use", "id": f"t{i}", "name": n, "input": a} for i, (n, a) in enumerate(calls)]
        return {"text": text, "tool_calls": [{"id": f"t{i}", "name": n, "input": a} for i, (n, a) in enumerate(calls)],
                "raw_content": raw, "usage": {}}


def test_numbers_come_from_the_engine(sample_case):
    llm = ScriptedLLM([
        ("", [("simulate", {"changes": {"cap_amount": 180000}})]),
        ("Mit Deckel 180.000 € steigt die Summe.", []),
    ])
    a = Assistant(sample_case, llm).ask("Was kostet ein Deckel von 180.000 €?")
    assert a.tool_trace == [{"tool": "simulate", "input": {"changes": {"cap_amount": 180000}}, "error": False}]

    tool_result = json.loads(llm.seen[1]["messages"][-1]["content"][0]["content"])
    expected = calculate(sample_case.employees, sample_case.scheme.with_changes(cap_amount=180000)).total
    assert tool_result["result"]["summary"]["total"] == expected


def test_routes_qa_to_the_mid_model(sample_case):
    llm = ScriptedLLM([("ok", [])])
    Assistant(sample_case, llm).ask("Wie hoch ist der Median?")
    assert llm.seen[0]["model"] == "claude-sonnet-5-5"


def test_names_in_the_question_never_leave_the_process(sample_case):
    llm = ScriptedLLM([])
    name = sample_case.employees[16].name
    a = Assistant(sample_case, llm).ask(f"Wie viel bekommt {name}?")
    assert a.blocked
    assert llm.seen == []  # the model was never called


def test_nothing_sent_to_the_model_contains_personal_data(sample_case):
    llm = ScriptedLLM([
        ("", [("current_plan", {}), ("compare", {"scenarios": {"A": {}, "B": {"factor": 0.6}}}),
              ("fit_budget", {"budget": 6_000_000})]),
        ("fertig", []),
    ])
    Assistant(sample_case, llm).ask("Vergleiche bitte.")
    sent = json.dumps(llm.seen, ensure_ascii=False)
    for e in sample_case.employees:
        assert e.name not in sent
        assert e.birth_date.isoformat() not in sent
        assert f'"monthly_gross": {e.monthly_gross}' not in sent


def test_bad_tool_input_is_reported_to_the_model_not_raised(sample_case):
    llm = ScriptedLLM([
        ("", [("simulate", {"changes": {"faktor": 0.8}})]),  # typo the model might make
        ("Feld unbekannt.", []),
    ])
    a = Assistant(sample_case, llm).ask("Faktor 0,8?")
    assert a.tool_trace[0]["error"] is True
    assert "Unknown scheme fields" in llm.seen[1]["messages"][-1]["content"][0]["content"]


def test_loop_stops_after_max_steps(sample_case):
    llm = ScriptedLLM([("", [("current_plan", {})])] * 20)
    a = Assistant(sample_case, llm).ask("Endlosschleife?")
    assert len(llm.seen) == Assistant.MAX_STEPS
    assert "zu viele" in a.text


def test_header_mapping_output_is_validated():
    llm = ScriptedLLM([('{"birth_date": "Geburtstag", "monthly_gross": "Erfunden", "hack": "x"}', [])])
    out = map_headers(["Geburtstag", "Fixum"], ["birth_date", "monthly_gross"], llm)
    assert out == {"birth_date": "Geburtstag"}  # hallucinated header and unknown field dropped
    assert llm.seen[0]["model"] == "claude-haiku-5-5"
