"""What a language model is allowed to see.

Client data in a Sozialplan is about as sensitive as it gets: names, ages,
salaries, disabilities, family status. The rule in this codebase is simple:

    A cloud model never sees a name, a date of birth or a single salary.

``llm_view`` builds the only representation that crosses the process boundary.
Level "aggregates" (default) is statistics only. Level "pseudonymized" adds
per-person rows keyed by Personal-Nr. with age, tenure and amount, and is only
allowed when the model runs on our own hardware (see routing.py).
``assert_clean`` is a last line of defence that runs on every outgoing prompt.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from .engine import Result
from .model import Employee

Level = Literal["aggregates", "pseudonymized"]

BANDS = [(0, 10_000), (10_000, 25_000), (25_000, 50_000), (50_000, 100_000), (100_000, 10**12)]


class PrivacyViolation(RuntimeError):
    pass


def llm_view(result: Result, level: Level = "aggregates") -> dict[str, Any]:
    eligible = [l for l in result.lines if l.eligible]
    bands = []
    for lo, hi in BANDS:
        n = sum(1 for l in eligible if lo <= l.amount < hi)
        label = f"{lo:,}–{hi:,} €".replace(",", ".") if hi < 10**12 else f"ab {lo:,} €".replace(",", ".")
        bands.append({"band": label, "count": n})
    by_age = {}
    for lo, hi in [(18, 30), (30, 40), (40, 50), (50, 60), (60, 70)]:
        group = [l.amount for l in eligible if lo <= l.age < hi]
        by_age[f"{lo}–{hi - 1}"] = {"count": len(group),
                                    "avg": round(sum(group) / len(group)) if group else 0}
    view: dict[str, Any] = {
        "quota": round(result.quota, 6),
        "total_before_cut": round(result.total_gross),
        "summary": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in result.summary.items()},
        "distribution": bands,
        "by_age_group": by_age,
    }
    if level == "pseudonymized":
        view["rows"] = [
            {"id": l.id, "age": l.age, "tenure_years": l.tenure_years, "limit": l.limit,
             "amount": l.amount, "points": l.points}
            for l in result.lines
        ]
    return view


def _name_variants(name: str) -> set[str]:
    parts = name.split()
    if len(parts) < 2:
        return {name.lower()}
    first, last = " ".join(parts[:-1]), parts[-1]
    return {name.lower(), f"{last}, {first}".lower(), f"{last} {first}".lower()}


def assert_clean(payload: Any, employees: list[Employee]) -> None:
    """Raise if a full name or a birth date of the population appears in ``payload``.

    Surnames alone are not checked: "Winter" or "Sommer" are also ordinary
    words, and a guard that fires on every season is a guard people disable.
    """
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str)
    lowered = re.sub(r"\s+", " ", text.lower())
    for e in employees:
        if any(v in lowered for v in _name_variants(e.name)):
            raise PrivacyViolation(f"personal name of {e.id} in outgoing payload")
        if e.birth_date.isoformat() in text or e.birth_date.strftime("%d.%m.%Y") in text:
            raise PrivacyViolation(f"birth date of {e.id} in outgoing payload")
