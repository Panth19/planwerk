"""The AI layer: language in, engine calls out.

The model never does arithmetic on money. It translates a lawyer's question
("What if we raise the cap to 180k and drop the floor?") into engine calls,
reads the results and explains them. Every number in its answer comes from
``engine.py``, and everything it sees has passed ``privacy.assert_clean``.

Three jobs, three routes (see routing.py):
    ask()            scenario Q&A with tool use
    draft_memo()     a short memo for the partner
    map_headers()    fallback for unknown spreadsheet columns
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from . import audit
from .engine import calculate, compare, fit_budget
from .excel import FIELD_SYNONYMS
from .model import Case, Scheme
from .privacy import PrivacyViolation, assert_clean, llm_view
from .routing import Route, is_local, route

SYSTEM_QA = """You are the calculation assistant inside Planwerk, a Sozialplan tool used by
employment lawyers at a German law firm. You answer questions about severance
scenarios for one restructuring case.

Rules:
- Never compute amounts yourself. Call the tools; quote their numbers.
- Change only the parameters the user asked about; keep everything else as is.
- Answer in the language of the question. Be brief: lead with the number that
  answers the question, then at most three short sentences of context.
- Format money German-style when answering in German (1.234.567 €).
- You see aggregates, not people. If asked about a named person, say that names
  are not shared with you and ask for the Personal-Nr. instead.
- This is a calculation aid, not legal advice. Do not assess whether a scheme is
  lawful; you may point out which parameter drives a result.

Scheme fields you can change (JSON names): formula ("factor"|"divisor"), factor,
divisor, tenure_rounding ("months"|"full_years"|"half_up"), min_tenure_months,
floor_amount, cap_amount, retirement_age, retirement_cap_months, child_bonus,
disability_bonus, budget, budget_mode ("none"|"pro_rata"), rounding_step."""

SYSTEM_MEMO = """You write internal memos for an employment-law partner at a German law firm.
Write in German, plain and precise, max. 350 words, as Markdown with these
sections: Ausgangslage, Szenarien (a compact table), Bewertung der Stellschrauben,
Empfehlung für die Verhandlung. Use only the numbers provided. Mark it as a
calculation summary, not a legal opinion. No names of employees exist in your
input; do not invent any."""

TOOLS: list[dict[str, Any]] = [
    {
        "name": "current_plan",
        "description": "The current scheme and its result (aggregates only).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "simulate",
        "description": (
            "Recalculate with some scheme fields changed. Returns the changed scheme and its result. "
            "Does not modify the current plan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "changes": {"type": "object", "description": 'Scheme fields to override, e.g. {"cap_amount": 180000}'}
            },
            "required": ["changes"],
        },
    },
    {
        "name": "fit_budget",
        "description": (
            "Most generous factor (or smallest divisor) whose total stays within the given budget. "
            "Optional changes are applied first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"budget": {"type": "number"}, "changes": {"type": "object"}},
            "required": ["budget"],
        },
    },
    {
        "name": "compare",
        "description": (
            "Compare several named scenarios side by side. Each scenario is a set of changes to the current scheme."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"scenarios": {"type": "object", "additionalProperties": {"type": "object"}}},
            "required": ["scenarios"],
        },
    },
]


class LLM(Protocol):
    def complete(
        self, r: Route, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> dict[str, Any]:
        """Return {"text": str, "tool_calls": [{"id", "name", "input"}], "raw_content": Any}."""
        ...


class AnthropicLLM:
    def __init__(self) -> None:
        import anthropic  # optional dependency

        self.client = anthropic.Anthropic(timeout=90.0, max_retries=2)

    def complete(self, r, system, messages, tools):
        kw = r.api_kwargs()
        if tools:
            kw["tools"] = tools
        resp = self.client.messages.create(system=system, messages=messages, **kw)
        text = "".join(b.text for b in resp.content if b.type == "text")
        calls = [{"id": b.id, "name": b.name, "input": b.input} for b in resp.content if b.type == "tool_use"]
        return {
            "text": text,
            "tool_calls": calls,
            "raw_content": resp.content,
            "usage": {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens},
        }


class LocalLLM:
    """OpenAI-compatible endpoint on our own hardware (vLLM, llama.cpp server, ...)."""

    def __init__(self) -> None:
        self.base = os.environ.get("PLANWERK_LOCAL_URL", "http://localhost:8000/v1")

    def complete(self, r, system, messages, tools):
        oa_msgs = [{"role": "system", "content": system}] + [_to_openai(m) for m in messages]
        oa_msgs = [m for mm in oa_msgs for m in (mm if isinstance(mm, list) else [mm])]
        body: dict[str, Any] = {"model": r.model, "messages": oa_msgs, "max_tokens": r.max_tokens}
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]},
                }
                for t in tools
            ]
        resp = httpx.post(f"{self.base}/chat/completions", json=body, timeout=120)
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        calls = [
            {"id": c["id"], "name": c["function"]["name"], "input": json.loads(c["function"]["arguments"] or "{}")}
            for c in msg.get("tool_calls") or []
        ]
        raw = ([{"type": "text", "text": msg["content"]}] if msg.get("content") else []) + [
            {"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["input"]} for c in calls
        ]
        usage = resp.json().get("usage") or {}
        return {
            "text": msg.get("content") or "",
            "tool_calls": calls,
            "raw_content": raw,
            "usage": {"in": usage.get("prompt_tokens", 0), "out": usage.get("completion_tokens", 0)},
        }


def _to_openai(m: dict[str, Any]) -> Any:
    """Translate one Anthropic-style message into OpenAI chat format."""
    if isinstance(m["content"], str):
        return {"role": m["role"], "content": m["content"]}
    out: list[dict[str, Any]] = []
    if m["role"] == "assistant":
        text = "".join(b["text"] for b in m["content"] if b.get("type") == "text")
        calls = [
            {"id": b["id"], "type": "function", "function": {"name": b["name"], "arguments": json.dumps(b["input"])}}
            for b in m["content"]
            if b.get("type") == "tool_use"
        ]
        out.append({"role": "assistant", "content": text, **({"tool_calls": calls} if calls else {})})
    else:
        for b in m["content"]:
            if b.get("type") == "tool_result":
                out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]})
            elif b.get("type") == "text":
                out.append({"role": "user", "content": b["text"]})
    return out


def default_llm() -> LLM:
    return LocalLLM() if is_local() else AnthropicLLM()


# --------------------------------------------------------------------------- #


@dataclass
class Answer:
    text: str
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    blocked: bool = False


def _serialize_content(raw: Any) -> list[dict[str, Any]]:
    """Turn a model response into message blocks we can send back unchanged.

    Thinking blocks must be passed back as they came (with signature) when the
    model thinks between tool calls; empty text blocks are rejected by the API.
    """
    out: list[dict[str, Any]] = []
    for b in raw:
        if isinstance(b, dict):
            if not (b.get("type") == "text" and not b.get("text")):
                out.append(b)
        elif b.type == "text":
            if b.text:
                out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        elif b.type == "thinking":
            out.append({"type": "thinking", "thinking": b.thinking, "signature": b.signature})
        elif b.type == "redacted_thinking":
            out.append({"type": "redacted_thinking", "data": b.data})
    return out


class Assistant:
    MAX_STEPS = 8

    def __init__(self, case: Case, llm: LLM | None = None) -> None:
        self.case = case
        self.llm = llm or default_llm()
        self.level = route("scenario_qa").privacy_level

    # ---- tools ------------------------------------------------------------ #

    def _scheme(self, changes: dict[str, Any] | None) -> Scheme:
        return self.case.scheme.with_changes(**(changes or {}))

    def _tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        emps = self.case.employees
        if name == "current_plan":
            return {
                "scheme": self.case.scheme.to_json(),
                "result": llm_view(calculate(emps, self.case.scheme), self.level),
            }
        if name == "simulate":
            s = self._scheme(args.get("changes"))
            return {"scheme": s.to_json(), "result": llm_view(calculate(emps, s), self.level)}
        if name == "fit_budget":
            return fit_budget(emps, self._scheme(args.get("changes")), float(args["budget"])).to_json()
        if name == "compare":
            res = compare(emps, {k: self._scheme(v) for k, v in args["scenarios"].items()})
            return {
                k: {
                    "changes": args["scenarios"][k],
                    "total": v["total"],
                    "quota": v["quota"],
                    "eligible": v["summary"]["eligible"],
                    "median": v["summary"]["median"],
                    "max": v["summary"]["max"],
                    "limits": v["summary"]["limits"],
                }
                for k, v in res.items()
            }
        raise ValueError(f"unknown tool {name}")

    # ---- loop ------------------------------------------------------------- #

    def ask(self, question: str) -> Answer:
        try:
            assert_clean(question, self.case.employees)
        except PrivacyViolation:
            audit.event("assistant.blocked", reason="name_in_question")
            return Answer(
                "Namen werden nicht an das Sprachmodell übermittelt. Bitte fragen Sie mit der "
                "Personal-Nr. (z. B. MA-017) oder ohne Personenbezug.",
                blocked=True,
            )

        r = route("scenario_qa")
        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
        trace: list[dict[str, Any]] = []
        tokens = {"in": 0, "out": 0}
        with audit.timed("assistant.ask", model=r.model, privacy=self.level) as info:
            for step in range(self.MAX_STEPS):
                out = self.llm.complete(r, SYSTEM_QA, messages, TOOLS)
                for k in tokens:
                    tokens[k] += (out.get("usage") or {}).get(k, 0)
                info.update(tokens_in=tokens["in"], tokens_out=tokens["out"])
                if not out["tool_calls"]:
                    info.update(steps=step + 1, tools=[t["tool"] for t in trace])
                    return Answer(out["text"].strip(), trace)
                messages.append({"role": "assistant", "content": _serialize_content(out["raw_content"])})
                results = []
                for call in out["tool_calls"]:
                    try:
                        payload = self._tool(call["name"], call["input"] or {})
                        is_error = False
                    except (ValueError, KeyError, TypeError) as exc:
                        payload, is_error = {"error": str(exc)}, True
                    assert_clean(payload, self.case.employees)  # hard stop, never caught
                    trace.append({"tool": call["name"], "input": call["input"], "error": is_error})
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call["id"],
                            "content": json.dumps(payload, ensure_ascii=False),
                            "is_error": is_error,
                        }
                    )
                messages.append({"role": "user", "content": results})
            info.update(steps=self.MAX_STEPS, aborted=True)
        return Answer("Die Anfrage brauchte zu viele Rechenschritte. Bitte enger formulieren.", trace)

    def draft_memo(self, scenarios: dict[str, dict[str, Any]]) -> str:
        r = route("partner_memo")
        res = compare(self.case.employees, {k: self._scheme(v) for k, v in scenarios.items()})
        payload = {
            "case": "Restrukturierung, " + str(len(self.case.employees)) + " betroffene Arbeitsverhältnisse",
            "base_scheme": self.case.scheme.to_json(),
            "scenarios": {
                k: {"changes": scenarios[k], "total": v["total"], "quota": v["quota"], "summary": v["summary"]}
                for k, v in res.items()
            },
        }
        assert_clean(payload, self.case.employees)
        with audit.timed("assistant.memo", model=r.model, scenarios=len(scenarios)):
            messages = [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
            out = self.llm.complete(r, SYSTEM_MEMO, messages, None)
        return out["text"].strip()


def map_headers(unmapped: list[str], missing: list[str], llm: LLM | None = None) -> dict[str, str]:
    """Ask a small model which unknown header means which missing field.

    Sends header names only. The answer is validated: unknown fields or
    headers that were not in the input are dropped, never trusted.
    """
    if not unmapped or not missing:
        return {}
    llm = llm or default_llm()
    r = route("header_mapping")
    prompt = json.dumps(
        {
            "unknown_headers": unmapped,
            "missing_fields": missing,
            "field_meaning": {f: FIELD_SYNONYMS[f][:3] for f in missing},
        },
        ensure_ascii=False,
    )
    out = llm.complete(
        r,
        "Map spreadsheet column headers to fields. Reply with a JSON object "
        "{field: header} only. Leave out fields with no confident match.",
        [{"role": "user", "content": prompt}],
        None,
    )
    try:
        raw = json.loads(out["text"].strip().removeprefix("```json").removesuffix("```").strip())
    except json.JSONDecodeError:
        return {}
    return {f: h for f, h in raw.items() if f in missing and h in unmapped}
