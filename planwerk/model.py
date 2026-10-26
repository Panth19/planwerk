"""Data model for a Sozialplan case.

Everything here is plain data. The calculation lives in ``engine.py`` and is
mirrored 1:1 in ``web/engine.js``; field names are identical in both so the
parity test can compare JSON output directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace
from datetime import date
from typing import Any, Literal

Formula = Literal["factor", "divisor"]
TenureRounding = Literal["months", "full_years", "half_up"]
BudgetMode = Literal["none", "pro_rata"]


@dataclass(frozen=True)
class Employee:
    """One person in Anlage 1 (the severance list).

    ``id`` is the stable pseudonym used everywhere outside the UI.
    ``name`` never leaves the process: not in logs, not in LLM prompts.
    """

    id: str
    name: str
    birth_date: date
    entry_date: date
    monthly_gross: float  # Bruttomonatsgehalt in EUR
    children: int = 0  # unterhaltsberechtigte Kinder
    married: bool = False  # verheiratet / eingetragene Lebenspartnerschaft
    disabled: bool = False  # schwerbehindert / gleichgestellt (GdB >= 50)

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["birth_date"] = self.birth_date.isoformat()
        d["entry_date"] = self.entry_date.isoformat()
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Employee":
        return cls(
            id=str(d["id"]),
            name=str(d.get("name", d["id"])),
            birth_date=date.fromisoformat(str(d["birth_date"])[:10]),
            entry_date=date.fromisoformat(str(d["entry_date"])[:10]),
            monthly_gross=float(d["monthly_gross"]),
            children=int(d.get("children", 0) or 0),
            married=_truthy(d.get("married", False)),
            disabled=_truthy(d.get("disabled", False)),
        )


@dataclass(frozen=True)
class Scheme:
    """The negotiated parameters of a Sozialplan (§§ of the agreement)."""

    stichtag: date = date(2026, 12, 31)

    # § 2 Abfindung
    formula: Formula = "factor"
    factor: float = 0.75  # Standardformel: BZ x Brutto x Faktor
    divisor: float = 80.0  # Divisorformel: Alter x BZ x Brutto / Divisor
    tenure_rounding: TenureRounding = "half_up"
    min_tenure_months: int = 6  # Anspruch erst ab ... Monaten BZ

    # § 3 Mindest- und Höchstbetrag
    floor_amount: float = 5_000.0  # Sockelbetrag
    cap_amount: float = 150_000.0  # Höchstbetrag (0 = kein Deckel)

    # § 4 Rentennahe Jahrgänge
    retirement_age: int = 63  # 0 = keine Sonderregel
    retirement_cap_months: float = 12.0

    # § 5 Zuschläge
    child_bonus: float = 3_000.0
    disability_bonus: float = 5_000.0

    # § 6 Sozialplanvolumen
    budget: float = 0.0  # 0 = kein Volumen vereinbart
    budget_mode: BudgetMode = "none"

    # Rundung der Einzelbeträge (1, 10 oder 100 EUR)
    rounding_step: float = 1.0

    def with_changes(self, **changes: Any) -> "Scheme":
        known = {f.name for f in fields(self)}
        unknown = set(changes) - known
        if unknown:
            raise ValueError(f"Unknown scheme fields: {sorted(unknown)}")
        if "stichtag" in changes and isinstance(changes["stichtag"], str):
            changes["stichtag"] = date.fromisoformat(changes["stichtag"])
        return replace(self, **changes)

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["stichtag"] = self.stichtag.isoformat()
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Scheme":
        return cls().with_changes(**d)


@dataclass(frozen=True)
class PointsScheme:
    """Punkteschema for the Sozialauswahl (§ 1 Abs. 3 KSchG).

    Defaults follow the scheme the BAG has accepted many times:
    1 point per year of age, 1 per year of service (2 from year 11),
    4 per child, 4 if married, 5 for Schwerbehinderung.
    """

    per_year_age: int = 1
    per_year_tenure: int = 1
    per_year_tenure_after_10: int = 2
    per_child: int = 4
    married: int = 4
    disabled: int = 5


@dataclass
class Case:
    """A named case: employees plus scheme. Stored as JSON on disk."""

    title: str
    employees: list[Employee]
    scheme: Scheme = field(default_factory=Scheme)
    synthetic: bool = True

    def to_json(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "synthetic": self.synthetic,
            "scheme": self.scheme.to_json(),
            "employees": [e.to_json() for e in self.employees],
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Case":
        return cls(
            title=d.get("title", "Unbenannter Fall"),
            employees=[Employee.from_json(e) for e in d["employees"]],
            scheme=Scheme.from_json(d.get("scheme", {})),
            synthetic=bool(d.get("synthetic", False)),
        )


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return str(v).strip().lower() in {"1", "true", "ja", "yes", "x", "j", "y", "wahr"}
