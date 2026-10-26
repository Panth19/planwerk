"""Sozialplan calculation engine.

Rules (see docs/RULES.md for the legal background):

1.  Tenure (Betriebszugehörigkeit) and age are measured at the Stichtag.
2.  Employees below ``min_tenure_months`` have no claim.
3.  Base amount:
      factor  formula: tenure x monthly_gross x factor
      divisor formula: age x tenure x monthly_gross / divisor
4.  Sockelbetrag lifts the base, Höchstbetrag caps it.
5.  Rentennahe Jahrgänge: from ``retirement_age`` the base is limited to
    ``retirement_cap_months`` monthly salaries.
6.  Zuschläge for children and Schwerbehinderung are added on top.
7.  If a budget is set with mode ``pro_rata`` and the sum exceeds it, every
    amount is cut by the same quota and rounded *down*, so the budget holds.
8.  Each amount is rounded to ``rounding_step`` (half up, like Excel ROUND).

PARITY CONTRACT: ``web/engine.js`` performs exactly the same floating point
operations in exactly the same order. If you change arithmetic here, change it
there and run ``pytest tests/test_js_parity.py``.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date
from statistics import median
from typing import Any, Iterable

from .model import Employee, PointsScheme, Scheme

FIT_FACTOR_MAX_THOUSANDTHS = 10_000  # factor search space 0.000 .. 10.000
FIT_DIVISOR_RANGE_TENTHS = (10, 10_000)  # divisor search space 1.0 .. 1000.0


# --------------------------------------------------------------------------- #
# Primitive helpers (mirrored in engine.js)
# --------------------------------------------------------------------------- #


def full_months(start: date, end: date) -> int:
    """Completed months between two dates (0 if end is before start)."""
    m = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        m -= 1
    return max(m, 0)


def age_at(birth: date, ref: date) -> int:
    a = ref.year - birth.year
    if (ref.month, ref.day) < (birth.month, birth.day):
        a -= 1
    return a


def tenure_years(months: int, mode: str) -> float:
    if mode == "months":
        return months / 12
    if mode == "full_years":
        return float(months // 12)
    if mode == "half_up":  # angefangene Jahre ab 6 Monaten zählen voll
        return float((months + 6) // 12)
    raise ValueError(f"unknown tenure_rounding: {mode}")


def _excel_precision(x: float) -> float:
    """Spreadsheets compute on 15 significant digits before rounding."""
    return float(f"{x:.15g}")


def round_step(x: float, step: float, down: bool = False) -> float:
    """Round to a multiple of ``step``. Half up like Excel ROUND, or down."""
    v = _excel_precision(x / step)
    n = math.floor(v) if down else math.floor(v + 0.5)
    return n * step


# --------------------------------------------------------------------------- #
# Per-employee calculation
# --------------------------------------------------------------------------- #


@dataclass
class Line:
    """One row of Anlage 1, fully explained."""

    id: str
    name: str
    age: int
    tenure_months: int
    tenure_years: float
    monthly_gross: float
    children: int
    married: bool
    disabled: bool
    eligible: bool
    base_raw: float  # formula result before Sockel/Deckel
    base: float  # after Sockel, Deckel, Rentennähe
    limit: str  # "", "floor", "cap", "retirement", "not_eligible"
    bonus: float  # Zuschläge
    gross: float  # base + bonus, before quota
    amount: float  # payable, rounded
    points: int  # Sozialauswahl points

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def gross_line(e: Employee, s: Scheme, points: PointsScheme) -> Line:
    months = full_months(e.entry_date, s.stichtag)
    tenure = tenure_years(months, s.tenure_rounding)
    age = age_at(e.birth_date, s.stichtag)
    eligible = months >= s.min_tenure_months

    if s.formula == "factor":
        base_raw = tenure * e.monthly_gross * s.factor
    elif s.formula == "divisor":
        base_raw = age * tenure * e.monthly_gross / s.divisor
    else:
        raise ValueError(f"unknown formula: {s.formula}")

    limit = ""
    base = base_raw
    if s.floor_amount > 0 and base < s.floor_amount:
        base = s.floor_amount
        limit = "floor"
    if s.cap_amount > 0 and base > s.cap_amount:
        base = s.cap_amount
        limit = "cap"
    if s.retirement_age > 0 and age >= s.retirement_age:
        r_cap = s.retirement_cap_months * e.monthly_gross
        if base > r_cap:
            base = r_cap
            limit = "retirement"

    bonus = e.children * s.child_bonus + (s.disability_bonus if e.disabled else 0.0)
    gross = base + bonus

    if not eligible:
        base_raw = base = bonus = gross = 0.0
        limit = "not_eligible"

    return Line(
        id=e.id,
        name=e.name,
        age=age,
        tenure_months=months,
        tenure_years=tenure,
        monthly_gross=e.monthly_gross,
        children=e.children,
        married=e.married,
        disabled=e.disabled,
        eligible=eligible,
        base_raw=base_raw,
        base=base,
        limit=limit,
        bonus=bonus,
        gross=gross,
        amount=0.0,
        points=social_points(age, months, e, points),
    )


def social_points(age: int, months: int, e: Employee, p: PointsScheme) -> int:
    years = months // 12
    tenure_pts = min(years, 10) * p.per_year_tenure + max(years - 10, 0) * p.per_year_tenure_after_10
    return (
        age * p.per_year_age
        + tenure_pts
        + e.children * p.per_child
        + (p.married if e.married else 0)
        + (p.disabled if e.disabled else 0)
    )


# --------------------------------------------------------------------------- #
# Whole plan
# --------------------------------------------------------------------------- #


@dataclass
class Result:
    lines: list[Line]
    quota: float  # 1.0 = no cut
    total_gross: float
    total: float
    summary: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "quota": self.quota,
            "total_gross": self.total_gross,
            "total": self.total,
            "summary": self.summary,
            "lines": [l.to_json() for l in self.lines],
        }


def calculate(
    employees: Iterable[Employee], scheme: Scheme, points: PointsScheme | None = None
) -> Result:
    points = points or PointsScheme()
    lines = [gross_line(e, scheme, points) for e in employees]

    total_gross = 0.0
    for l in lines:
        total_gross += l.gross

    quota = 1.0
    cut = scheme.budget_mode == "pro_rata" and scheme.budget > 0 and total_gross > scheme.budget
    if cut:
        quota = scheme.budget / total_gross

    total = 0.0
    for l in lines:
        l.amount = round_step(l.gross * quota, scheme.rounding_step, down=cut)
        total += l.amount

    return Result(lines, quota, total_gross, total, summarize(lines, total, scheme))


def summarize(lines: list[Line], total: float, scheme: Scheme) -> dict[str, Any]:
    paid = [l.amount for l in lines if l.eligible]
    by_limit: dict[str, int] = {"floor": 0, "cap": 0, "retirement": 0, "not_eligible": 0}
    for l in lines:
        if l.limit:
            by_limit[l.limit] += 1
    # Plain loop, not sum(): Python 3.12+ sum() uses compensated summation,
    # JavaScript does not, and the parity test compares results bit for bit.
    salary_sum = 0.0
    for l in lines:
        if l.eligible:
            salary_sum += l.monthly_gross
    return {
        "headcount": len(lines),
        "eligible": len(paid),
        "total": total,
        "average": (total / len(paid)) if paid else 0.0,
        "median": float(median(paid)) if paid else 0.0,
        "min": min(paid) if paid else 0.0,
        "max": max(paid) if paid else 0.0,
        "months_equivalent": (total / salary_sum) if salary_sum else 0.0,
        "limits": by_limit,
        "budget": scheme.budget,
        "budget_delta": (scheme.budget - total) if scheme.budget > 0 else None,
    }


# --------------------------------------------------------------------------- #
# Budget fitting
# --------------------------------------------------------------------------- #


@dataclass
class Fit:
    feasible: bool
    parameter: str  # "factor" or "divisor"
    value: float | None
    total: float | None
    budget: float
    evaluations: int
    note: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def fit_budget(
    employees: list[Employee], scheme: Scheme, budget: float, points: PointsScheme | None = None
) -> Fit:
    """Find the most generous formula parameter whose total stays within budget.

    Searches whole thousandths of the factor (0.725) or tenths of the divisor
    (82.5), the precision a Sozialplan is actually written in. Totals are
    monotonic in the parameter, so integer bisection is exact.
    """
    base = scheme.with_changes(budget=0.0, budget_mode="none")
    evals = 0

    def total_for(s: Scheme) -> float:
        nonlocal evals
        evals += 1
        return calculate(employees, s, points).total

    if scheme.formula == "factor":
        if total_for(base.with_changes(factor=0.0)) > budget:
            return Fit(False, "factor", None, None, budget, evals,
                       "Sockelbeträge und Zuschläge allein übersteigen das Volumen.")
        lo, hi = 0, FIT_FACTOR_MAX_THOUSANDTHS  # invariant: total(lo) <= budget
        if total_for(base.with_changes(factor=hi / 1000)) <= budget:
            lo = hi
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if total_for(base.with_changes(factor=mid / 1000)) <= budget:
                lo = mid
            else:
                hi = mid
        value = lo / 1000
        total = total_for(base.with_changes(factor=value))
        return Fit(True, "factor", value, total, budget, evals,
                   f"Höchster Faktor auf drei Nachkommastellen: {value:.3f}")

    lo_t, hi_t = FIT_DIVISOR_RANGE_TENTHS  # invariant: total(hi) <= budget
    if total_for(base.with_changes(divisor=hi_t / 10)) > budget:
        return Fit(False, "divisor", None, None, budget, evals,
                   "Auch mit dem größten Divisor wird das Volumen überschritten.")
    if total_for(base.with_changes(divisor=lo_t / 10)) <= budget:
        hi_t = lo_t
    while hi_t - lo_t > 1:
        mid = (lo_t + hi_t) // 2
        if total_for(base.with_changes(divisor=mid / 10)) <= budget:
            hi_t = mid
        else:
            lo_t = mid
    value = hi_t / 10
    total = total_for(base.with_changes(divisor=value))
    return Fit(True, "divisor", value, total, budget, evals,
               f"Kleinster Divisor auf eine Nachkommastelle: {value:.1f}")


def compare(employees: list[Employee], scenarios: dict[str, Scheme]) -> dict[str, Any]:
    """Side-by-side totals for named scenarios (used by MCP and the assistant)."""
    out = {}
    for name, s in scenarios.items():
        r = calculate(employees, s)
        out[name] = {
            "scheme": s.to_json(),
            "total": r.total,
            "quota": r.quota,
            "summary": r.summary,
        }
    return out
