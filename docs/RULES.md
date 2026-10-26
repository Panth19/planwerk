# Calculation rules and their background

Planwerk calculates; it does not judge whether a Sozialplan is lawful. This page explains
where each rule comes from, so whoever changes the engine knows what they are touching.
Not legal advice.

## Context

A **Sozialplan** is the agreement between employer and works council that compensates or
mitigates the economic disadvantages employees suffer from a *Betriebsänderung*
(§ 112 Abs. 1 Satz 2 BetrVG, the change itself defined in § 111 BetrVG). If the parties do not
agree, the Einigungsstelle decides (§ 112 Abs. 4 BetrVG) and must keep the plan economically
bearable for the company (§ 112 Abs. 5 BetrVG). In practice that means two numbers are
negotiated at the same time: a **formula** and a **total volume** (Sozialplanvolumen,
Dotierungsrahmen). Planwerk exists to move between the two quickly.

The list of affected employees with their individual amounts is usually attached as
**Anlage 1**.

## Order of calculation (engine.py, engine.js, Excel columns M to S)

| Step | Rule | Scheme field |
|---|---|---|
| 1 | Age and tenure at the **Stichtag**, in completed years and months | `stichtag` |
| 2 | No claim below a minimum tenure | `min_tenure_months` |
| 3 | **Formelbetrag**, standard or divisor formula | `formula`, `factor`, `divisor` |
| 4 | **Sockelbetrag** lifts small amounts | `floor_amount` |
| 5 | **Höchstbetrag** caps large ones | `cap_amount` |
| 6 | **Rentennahe Jahrgänge**: limit in monthly salaries | `retirement_age`, `retirement_cap_months` |
| 7 | **Zuschläge** for children and Schwerbehinderung, on top of the cap | `child_bonus`, `disability_bonus` |
| 8 | **Anteilige Kürzung** if the sum exceeds the volume | `budget`, `budget_mode` |
| 9 | **Rounding** of each amount | `rounding_step` |

The order matters and is a negotiated point, not a law of nature. Examples: whether the
Zuschläge fall under the Höchstbetrag (here: no), or whether the Sockelbetrag applies before
the rentennahe limit (here: yes, so a person close to retirement can end up below the Sockel).

### Formulas

- **Standardformel:** Betriebszugehörigkeit × Bruttomonatsgehalt × Faktor.
  For orientation: § 1a KSchG uses 0.5 monthly salaries per year of service. Negotiated
  Sozialpläne are commonly above that.
- **Divisorformel:** Lebensalter × Betriebszugehörigkeit × Bruttomonatsgehalt ÷ Divisor.
  Gives older employees more, because their chances on the labour market are typically
  worse. Age-based differentiation in a Sozialplan is permitted within the limits of
  § 10 Satz 3 Nr. 6 AGG.

### Tenure rounding

`half_up` counts a started year as full from six completed months. § 1a Abs. 2 KSchG rounds
up periods of *more than* six months. With month-level data those are the same unless the
exact day matters; a Sozialplan should say which it means. `full_years` and `months` exist
because both are found in practice.

### Rentennahe Jahrgänge

People who can draw a pension soon after leaving lose less income. Sozialpläne may give them
less (§ 10 Satz 3 Nr. 6 AGG). Planwerk models the common form: from a given age, at most N
monthly salaries. Every change to this rule must go past the `legal-rules-reviewer`.

### Volume and pro-rata cut

If `budget_mode` is `pro_rata` and the sum exceeds the volume, every amount is multiplied by
the same quota and rounded **down**, so the volume is never exceeded. The alternative most
negotiations use is to fit the formula itself to the volume: `fit_budget` finds the highest
factor (in thousandths) or the lowest divisor (in tenths) that stays within it. Thousandths
and tenths, because that is the precision a Sozialplan is written in.

## Sozialauswahl points (separate topic)

Who is dismissed and what they receive are different questions. The Sozialauswahl
(§ 1 Abs. 3 KSchG) weighs tenure, age, maintenance obligations and Schwerbehinderung; a
points scheme may be agreed (§ 1 Abs. 4 KSchG). Planwerk shows points per person using a
widely used scheme: 1 point per year of age, 1 per year of service up to 10 years and
2 per year after that, 4 per child, 8 for a spouse, 5 for Schwerbehinderung. The points do
not influence any amount.

## Glossary

| German | Meaning in Planwerk | Code |
|---|---|---|
| Abfindung | severance amount | `amount` |
| Anlage 1 | the per-person list | export sheet "Anlage 1" |
| Betriebszugehörigkeit (BZ) | tenure | `tenure_months`, `tenure_years` |
| Bruttomonatsgehalt | monthly gross salary | `monthly_gross` |
| Höchstbetrag | cap | `cap_amount` |
| Kürzungsquote | pro-rata quota | `quota` |
| Sockelbetrag | minimum amount | `floor_amount` |
| Sozialplanvolumen | total budget | `budget` |
| Stichtag | reference date | `stichtag` |
| Zuschläge | supplements | `bonus` |
