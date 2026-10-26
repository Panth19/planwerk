import io
import json
import logging

import pytest

from planwerk import audit
from planwerk.engine import calculate
from planwerk.privacy import PrivacyViolation, assert_clean, llm_view


def test_llm_view_has_no_personal_rows_by_default(sample_case):
    view = llm_view(calculate(sample_case.employees, sample_case.scheme))
    assert "rows" not in view
    assert_clean(view, sample_case.employees)


def test_guard_catches_names_in_any_order_and_birth_dates(sample_case):
    e = sample_case.employees[0]
    first, last = e.name.split()
    for leak in (e.name, f"{last}, {first}", {"note": e.name.upper()}, e.birth_date.strftime("%d.%m.%Y")):
        with pytest.raises(PrivacyViolation):
            assert_clean(leak, sample_case.employees)


def test_guard_ignores_ordinary_words(sample_case):
    # Surnames like Winter or Sommer are also ordinary German words.
    assert_clean("Was passiert, wenn der Sozialplan im Winter oder Sommer greift?", sample_case.employees)


def test_logs_contain_no_personal_data(sample_case, monkeypatch):
    stream = io.StringIO()
    log = audit.get_logger()
    h = logging.StreamHandler(stream)
    h.setFormatter(audit.JsonFormatter())
    log.addHandler(h)
    try:
        with audit.timed("test.calculate", headcount=len(sample_case.employees)) as info:
            r = calculate(sample_case.employees, sample_case.scheme)
            info.update(total=r.total)
    finally:
        log.removeHandler(h)
    out = stream.getvalue()
    assert json.loads(out.splitlines()[-1])["event"] == "test.calculate"
    for e in sample_case.employees:
        assert e.name not in out
        assert e.birth_date.isoformat() not in out
