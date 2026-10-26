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
    eligible = [line for line in result.lines if line.eligible]
    bands = []
    for lo, hi in BANDS:
        n = sum(1 for line in eligible if lo <= line.amount < hi)
        label = f"{lo:,}–{hi:,} €".replace(",", ".") if hi < 10**12 else f"ab {lo:,} €".replace(",", ".")
        bands.append({"band": label, "count": n})
    by_age = {}
    for lo, hi in [(0, 30), (30, 40), (40, 50), (50, 60), (60, 200)]:
        group = [line.amount for line in eligible if lo <= line.age < hi]
        label = "unter 30" if lo == 0 else ("ab 60" if hi == 200 else f"{lo}–{hi - 1}")
        by_age[label] = {"count": len(group), "avg": round(sum(group) / len(group)) if group else 0}
    view: dict[str, Any] = {
        "quota": round(result.quota, 6),
        "total_before_cut": round(result.total_gross),
        "summary": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in result.summary.items()},
        "distribution": bands,
        "by_age_group": by_age,
    }
    if level == "pseudonymized":
        view["rows"] = [
            {
                "id": line.id,
                "age": line.age,
                "tenure_years": line.tenure_years,
                "limit": line.limit,
                "amount": line.amount,
                "points": line.points,
            }
            for line in result.lines
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
