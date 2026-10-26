"""Engine rules, each pinned with a hand-calculated example."""

from datetime import date

import pytest

from planwerk.engine import (
    age_at,
    calculate,
    fit_budget,
    full_months,
    round_step,
    social_points,
    tenure_years,
)
from planwerk.model import Employee, PointsScheme, Scheme

STICHTAG = date(2026, 12, 31)


def emp(**kw) -> Employee:
    base = dict(
        id="T-1", name="Test Person",
        birth_date=date(1980, 6, 15), entry_date=date(2010, 3, 1),
        monthly_gross=4000.0,
    )
    base.update(kw)
    return Employee(**base)


def plain(**kw) -> Scheme:
    """Scheme with every special rule switched off."""
    s = dict(floor_amount=0, cap_amount=0, retirement_age=0, child_bonus=0,
             disability_bonus=0, tenure_rounding="full_years", min_tenure_months=0)
    s.update(kw)
    return Scheme(**s)


# --- dates ----------------------------------------------------------------- #

@pytest.mark.parametrize("start,end,months", [
    (date(2010, 3, 1), date(2026, 12, 31), 201),
    (date(2026, 1, 31), date(2026, 2, 28), 0),   # not a completed month
    (date(2026, 1, 15), date(2026, 2, 15), 1),
    (date(2027, 1, 1), date(2026, 12, 31), 0),   # entry after Stichtag
])
def test_full_months(start, end, months):
    assert full_months(start, end) == months


def test_age_counts_birthday_on_stichtag():
    assert age_at(date(1966, 12, 31), STICHTAG) == 60
    assert age_at(date(1967, 1, 1), STICHTAG) == 59


@pytest.mark.parametrize("months,mode,years", [
    (201, "full_years", 16.0),   # 16 years 9 months
    (201, "half_up", 17.0),      # >= 6 months counts as a started year
    (197, "half_up", 16.0),      # 16 years 5 months
    (198, "half_up", 17.0),      # exactly 6 months rounds up
    (201, "months", 16.75),
])
def test_tenure_rounding(months, mode, years):
    assert tenure_years(months, mode) == years


@pytest.mark.parametrize("x,step,down,expected", [
    (6001.5, 1, False, 6002),
    (6001.49, 1, False, 6001),
    (6001.99, 1, True, 6001),
    (12345, 10, False, 12350),
    (12344.9, 100, False, 12300),
    (1.005 * 1000, 1, False, 1005),   # float noise must not flip the result
])
def test_round_step(x, step, down, expected):
    assert round_step(x, step, down) == expected


# --- formulas -------------------------------------------------------------- #

def test_factor_formula():
    # 16 full years x 4,000 x 0.75 = 48,000
    r = calculate([emp()], plain(factor=0.75))
    assert r.lines[0].tenure_years == 16
    assert r.total == 48_000


def test_divisor_formula():
    # age 46 x 16 years x 4,000 / 80 = 36,800
    r = calculate([emp()], plain(formula="divisor", divisor=80))
    assert r.lines[0].age == 46
    assert r.total == 36_800


def test_floor_lifts_small_amounts():
    e = emp(entry_date=date(2025, 1, 1))  # 1 full year -> 3,000
    r = calculate([e], plain(floor_amount=5_000))
    assert r.lines[0].amount == 5_000
    assert r.lines[0].limit == "floor"


def test_cap_limits_base_but_not_bonus():
    e = emp(monthly_gross=12_000.0, children=2)  # 16 x 12,000 x 1.0 = 192,000
    r = calculate([e], plain(factor=1.0, cap_amount=150_000, child_bonus=3_000))
    line = r.lines[0]
    assert line.limit == "cap"
    assert line.base == 150_000
    assert line.amount == 156_000  # bonus comes on top of the cap


def test_retirement_near_cap():
    e = emp(birth_date=date(1962, 5, 1), entry_date=date(1990, 1, 1))  # age 64, 36 yrs
    r = calculate([e], plain(factor=1.0, retirement_age=63, retirement_cap_months=12))
    assert r.lines[0].limit == "retirement"
    assert r.total == 48_000  # 12 monthly salaries


def test_disability_bonus():
    r = calculate([emp(disabled=True)], plain(disability_bonus=5_000))
    assert r.total == 48_000 + 5_000


def test_min_tenure_excludes_recent_hires():
    e = emp(entry_date=date(2026, 9, 1), children=3)  # 3 months
    r = calculate([e], plain(min_tenure_months=6, child_bonus=3_000, floor_amount=5_000))
    assert not r.lines[0].eligible
    assert r.total == 0
    assert r.summary["eligible"] == 0


# --- budget ---------------------------------------------------------------- #

def test_pro_rata_cut_never_exceeds_budget():
    staff = [emp(id=f"T-{i}", monthly_gross=3000.0 + i * 137.0) for i in range(40)]
    s = plain(budget=1_000_000, budget_mode="pro_rata")
    r = calculate(staff, s)
    assert r.total_gross > 1_000_000
    assert r.quota < 1
    assert r.total <= 1_000_000
    assert 1_000_000 - r.total < len(staff)  # at most 1 EUR rounding loss per person


def test_pro_rata_inactive_when_under_budget():
    r = calculate([emp()], plain(budget=1_000_000, budget_mode="pro_rata"))
    assert r.quota == 1.0
    assert r.total == 48_000


def test_fit_factor_is_the_most_generous_within_budget():
    staff = [emp(id=f"T-{i}", monthly_gross=3000.0 + i * 211.0) for i in range(30)]
    s = plain()
    fit = fit_budget(staff, s, 1_500_000)
    assert fit.feasible
    assert calculate(staff, s.with_changes(factor=fit.value)).total <= 1_500_000
    assert calculate(staff, s.with_changes(factor=fit.value + 0.001)).total > 1_500_000


def test_fit_divisor():
    staff = [emp(id=f"T-{i}", monthly_gross=3000.0 + i * 211.0) for i in range(30)]
    s = plain(formula="divisor")
    fit = fit_budget(staff, s, 1_000_000)
    assert fit.feasible
    assert calculate(staff, s.with_changes(divisor=fit.value)).total <= 1_000_000
    assert calculate(staff, s.with_changes(divisor=round(fit.value - 0.1, 1))).total > 1_000_000


def test_fit_reports_infeasible_budget():
    staff = [emp(id=f"T-{i}") for i in range(10)]
    fit = fit_budget(staff, plain(floor_amount=20_000), 100_000)
    assert not fit.feasible


# --- Sozialauswahl --------------------------------------------------------- #

def test_social_points_bag_scheme():
    # age 46 -> 46; 16 years -> 10 + 6*2 = 22; 2 children -> 8; married 8; disabled 5
    e = emp(children=2, married=True, disabled=True)
    assert social_points(46, 201, e, PointsScheme()) == 46 + 22 + 8 + 8 + 5


def test_unknown_scheme_field_is_rejected():
    with pytest.raises(ValueError):
        Scheme().with_changes(faktor=0.8)


def test_exact_half_survives_float_noise():
    # Regression: 298 months = 24.8333.. years; x 5,980 x 0.75 = 111,377.50 exactly,
    # but binary floats give 111,377.4999999. Must round up, in engine and in Excel.
    e = emp(entry_date=date(2002, 2, 26), monthly_gross=5980.0)
    r = calculate([e], plain(tenure_rounding="months"))
    assert r.lines[0].tenure_months == 298
    assert r.total == 111_378
