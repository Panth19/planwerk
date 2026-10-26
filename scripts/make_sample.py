"""Generate the synthetic demo case.

Deterministic (fixed seed) so tests and screenshots are reproducible.
The company and every person in it are invented. Do not replace this file
with real client data; real cases live outside the repo (see SECURITY.md).

    python scripts/make_sample.py            # writes data/sample_case.json
"""

from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from planwerk.model import Case, Employee, Scheme  # noqa: E402

FIRST = (
    "Anna Ben Clara David Elif Felix Greta Hannes Ida Jonas Katrin Lukas Mara Niklas "
    "Olga Paul Rania Simon Tanja Ugur Vera Yusuf Zoe Jan Lea Malte Nora Tim Selin Kai "
    "Birgit Detlef Heike Jürgen Monika Rainer Sabine Uwe Petra Frank Dragan Ewa Marek"
).split()
LAST = (
    "Albers Brandt Celik Dietrich Engel Fuchs Gerber Hahn Jansen Kaya Lorenz Marx Nowak "
    "Otto Peters Quast Roth Sommer Thiel Ulrich Vogel Winter Yilmaz Zimmer Becker Kowalski "
    "Schreiber Haas Krüger Lindner Pohl Wagner Brückner Ostermann Petrović Szymańska"
).split()


def build(n: int = 140, seed: int = 1907) -> Case:
    rng = random.Random(seed)
    stichtag = date(2026, 12, 31)
    employees = []
    used: set[str] = set()
    for i in range(n):
        while True:
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if name not in used:
                used.add(name)
                break
        age = int(rng.triangular(21, 66, 48))
        birth = date(stichtag.year - age, 1, 1) + timedelta(days=rng.randint(0, 364))
        earliest_entry = max(date(birth.year + 17, 9, 1), date(1985, 1, 1))
        span = (stichtag - earliest_entry).days
        # Skew towards long tenure: a typical German manufacturing site.
        entry = earliest_entry + timedelta(days=int(span * rng.random() ** 1.6))
        if rng.random() < 0.04:  # a few very recent hires below the 6-month line
            entry = stichtag - timedelta(days=rng.randint(30, 170))
        level = rng.choices([0, 1, 2, 3], weights=[38, 34, 20, 8])[0]
        salary = [rng.uniform(2900, 3800), rng.uniform(3800, 5200),
                  rng.uniform(5200, 7400), rng.uniform(7400, 11800)][level]
        salary = round(salary / 10) * 10
        children = rng.choices([0, 1, 2, 3], weights=[48, 22, 22, 8])[0] if age < 58 else 0
        employees.append(Employee(
            id=f"MA-{i + 1:03d}",
            name=name,
            birth_date=birth,
            entry_date=entry,
            monthly_gross=float(salary),
            children=children,
            married=rng.random() < 0.55,
            disabled=rng.random() < 0.07,
        ))
    return Case(
        title="Halberg Feinmechanik GmbH, Werk Offenbach (synthetisch)",
        employees=employees,
        scheme=Scheme(budget=6_500_000.0),
        synthetic=True,
    )


if __name__ == "__main__":
    out = ROOT / "data" / "sample_case.json"
    out.write_text(json.dumps(build().to_json(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")
