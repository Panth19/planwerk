/*
 * Planwerk engine, browser edition.
 *
 * PARITY CONTRACT: a line-by-line mirror of planwerk/engine.py. Same
 * operations, same order, same field names, so tests/test_js_parity.py can
 * compare both engines' JSON output exactly. Change one, change both.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Planwerk = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const FIT_FACTOR_MAX_THOUSANDTHS = 10000;
  const FIT_DIVISOR_RANGE_TENTHS = [10, 10000];

  const DEFAULT_SCHEME = Object.freeze({
    stichtag: "2026-12-31",
    formula: "factor",
    factor: 0.75,
    divisor: 80.0,
    tenure_rounding: "half_up",
    min_tenure_months: 6,
    floor_amount: 5000.0,
    cap_amount: 150000.0,
    retirement_age: 63,
    retirement_cap_months: 12.0,
    child_bonus: 3000.0,
    disability_bonus: 5000.0,
    budget: 0.0,
    budget_mode: "none",
    rounding_step: 1.0,
  });

  const DEFAULT_POINTS = Object.freeze({
    per_year_age: 1,
    per_year_tenure: 1,
    per_year_tenure_after_10: 2,
    per_child: 4,
    married: 4,
    disabled: 5,
  });

  // Dates are handled as integer triples, never as Date objects:
  // no time zones, no daylight saving, identical to Python's date.
  function ymd(iso) {
    const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
    return { y, m, d };
  }

  function fullMonths(startIso, endIso) {
    const s = ymd(startIso), e = ymd(endIso);
    let m = (e.y - s.y) * 12 + (e.m - s.m);
    if (e.d < s.d) m -= 1;
    return Math.max(m, 0);
  }

  function ageAt(birthIso, refIso) {
    const b = ymd(birthIso), r = ymd(refIso);
    let a = r.y - b.y;
    if (r.m < b.m || (r.m === b.m && r.d < b.d)) a -= 1;
    return a;
  }

  function tenureYears(months, mode) {
    if (mode === "months") return months / 12;
    if (mode === "full_years") return Math.floor(months / 12);
    if (mode === "half_up") return Math.floor((months + 6) / 12);
    throw new Error("unknown tenure_rounding: " + mode);
  }

  function clean(x) {
    return Math.floor(x * 1e6 + 0.5) / 1e6;
  }

  function roundStep(x, step, down) {
    const v = clean(clean(x) / step);
    const n = down ? Math.floor(v) : Math.floor(v + 0.5);
    return n * step;
  }

  function socialPoints(age, months, e, p) {
    const years = Math.floor(months / 12);
    const tenurePts = Math.min(years, 10) * p.per_year_tenure + Math.max(years - 10, 0) * p.per_year_tenure_after_10;
    return age * p.per_year_age + tenurePts + e.children * p.per_child +
      (e.married ? p.married : 0) + (e.disabled ? p.disabled : 0);
  }

  function grossLine(e, s, p) {
    const months = fullMonths(e.entry_date, s.stichtag);
    const tenure = tenureYears(months, s.tenure_rounding);
    const age = ageAt(e.birth_date, s.stichtag);
    const eligible = months >= s.min_tenure_months;

    let baseRaw;
    if (s.formula === "factor") baseRaw = tenure * e.monthly_gross * s.factor;
    else if (s.formula === "divisor") baseRaw = age * tenure * e.monthly_gross / s.divisor;
    else throw new Error("unknown formula: " + s.formula);

    let limit = "";
    let base = baseRaw;
    if (s.floor_amount > 0 && base < s.floor_amount) { base = s.floor_amount; limit = "floor"; }
    if (s.cap_amount > 0 && base > s.cap_amount) { base = s.cap_amount; limit = "cap"; }
    if (s.retirement_age > 0 && age >= s.retirement_age) {
      const rCap = s.retirement_cap_months * e.monthly_gross;
      if (base > rCap) { base = rCap; limit = "retirement"; }
    }

    let bonus = e.children * s.child_bonus + (e.disabled ? s.disability_bonus : 0.0);
    let gross = base + bonus;

    if (!eligible) {
      baseRaw = base = bonus = gross = 0.0;
      limit = "not_eligible";
    }

    return {
      id: e.id, name: e.name, age, tenure_months: months, tenure_years: tenure,
      monthly_gross: e.monthly_gross, children: e.children, married: !!e.married, disabled: !!e.disabled,
      eligible, base_raw: baseRaw, base, limit, bonus, gross, amount: 0.0,
      points: socialPoints(age, months, e, p),
    };
  }

  function median(values) {
    const v = values.slice().sort((a, b) => a - b);
    const n = v.length, h = Math.floor(n / 2);
    return n % 2 ? v[h] : (v[h - 1] + v[h]) / 2;
  }

  function summarize(lines, total, s) {
    const paid = lines.filter((l) => l.eligible).map((l) => l.amount);
    const byLimit = { floor: 0, cap: 0, retirement: 0, not_eligible: 0 };
    for (const l of lines) if (l.limit) byLimit[l.limit] += 1;
    let salarySum = 0.0;
    for (const l of lines) if (l.eligible) salarySum += l.monthly_gross;
    return {
      headcount: lines.length,
      eligible: paid.length,
      total,
      average: paid.length ? total / paid.length : 0.0,
      median: paid.length ? median(paid) : 0.0,
      min: paid.length ? Math.min(...paid) : 0.0,
      max: paid.length ? Math.max(...paid) : 0.0,
      months_equivalent: salarySum ? total / salarySum : 0.0,
      limits: byLimit,
      budget: s.budget,
      budget_delta: s.budget > 0 ? s.budget - total : null,
    };
  }

  function calculate(employees, scheme, points) {
    const s = Object.assign({}, DEFAULT_SCHEME, scheme);
    const p = Object.assign({}, DEFAULT_POINTS, points || {});
    const lines = employees.map((e) => grossLine(e, s, p));

    let totalGross = 0.0;
    for (const l of lines) totalGross += l.gross;

    let quota = 1.0;
    const cut = s.budget_mode === "pro_rata" && s.budget > 0 && totalGross > s.budget;
    if (cut) quota = s.budget / totalGross;

    let total = 0.0;
    for (const l of lines) {
      l.amount = roundStep(l.gross * quota, s.rounding_step, cut);
      total += l.amount;
    }
    return { quota, total_gross: totalGross, total, summary: summarize(lines, total, s), lines };
  }

  function fitBudget(employees, scheme, budget, points) {
    const base = Object.assign({}, DEFAULT_SCHEME, scheme, { budget: 0.0, budget_mode: "none" });
    let evaluations = 0;
    const totalFor = (changes) => {
      evaluations += 1;
      return calculate(employees, Object.assign({}, base, changes), points).total;
    };

    if (base.formula === "factor") {
      if (totalFor({ factor: 0.0 }) > budget) {
        return { feasible: false, parameter: "factor", value: null, total: null, budget, evaluations,
          note: "Sockelbeträge und Zuschläge allein übersteigen das Volumen." };
      }
      let lo = 0, hi = FIT_FACTOR_MAX_THOUSANDTHS;
      if (totalFor({ factor: hi / 1000 }) <= budget) lo = hi;
      while (hi - lo > 1) {
        const mid = Math.floor((lo + hi) / 2);
        if (totalFor({ factor: mid / 1000 }) <= budget) lo = mid; else hi = mid;
      }
      const value = lo / 1000;
      const total = totalFor({ factor: value });
      return { feasible: true, parameter: "factor", value, total, budget, evaluations,
        note: "Höchster Faktor auf drei Nachkommastellen: " + value.toFixed(3) };
    }

    let [lo, hi] = FIT_DIVISOR_RANGE_TENTHS;
    if (totalFor({ divisor: hi / 10 }) > budget) {
      return { feasible: false, parameter: "divisor", value: null, total: null, budget, evaluations,
        note: "Auch mit dem größten Divisor wird das Volumen überschritten." };
    }
    if (totalFor({ divisor: lo / 10 }) <= budget) hi = lo;
    while (hi - lo > 1) {
      const mid = Math.floor((lo + hi) / 2);
      if (totalFor({ divisor: mid / 10 }) <= budget) hi = mid; else lo = mid;
    }
    const value = hi / 10;
    const total = totalFor({ divisor: value });
    return { feasible: true, parameter: "divisor", value, total, budget, evaluations,
      note: "Kleinster Divisor auf eine Nachkommastelle: " + value.toFixed(1) };
  }

  return { DEFAULT_SCHEME, DEFAULT_POINTS, fullMonths, ageAt, tenureYears, clean, roundStep,
    calculate, fitBudget, median };
});
