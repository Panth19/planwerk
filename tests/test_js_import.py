"""The browser importer (web/importer.js) must read client lists like the server does."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from planwerk.excel import read_employees

NODE = shutil.which("node")
pytestmark = [pytest.mark.node, pytest.mark.skipif(NODE is None, reason="Node.js not installed")]
HERE = Path(__file__).parent

FILES = {
    "german.csv": (
        "Pers.-Nr.;Mitarbeiter;Geb.-Datum;Eintrittsdatum;Monatsbrutto;Kinder;Familienstand;SB\n"
        "4711;Erika Muster;03.04.1971;01.08.1998;4.250,50 €;2;ja;nein\n"
        "4712;Max Muster;12.11.90;15.02.2019;3.980;0;nein;x\n"
        '4713;"Schmidt; Anna";01.01.1965;01.01.1990;"5.100,00";1;1;0\n'
        ";Summe;;;;;;\n"
    ),
    "english.csv": (
        "Employee ID,Full name,Date of birth,Start date,Monthly gross,Children,Married,Disabled\n"
        'E1,Jane Doe,1980-02-29,2005-03-01,"4,250.50",1,yes,no\n'
        "E2,John Roe,1975-12-31,2010-01-15,5200,0,no,yes\n"
    ),
    "messy.csv": (
        "﻿Nr;Name;Geburtsdatum;Eintritt;Brutto;Kinder\n"
        "1;Ok Person;01.01.1980;01.01.2000;4000;0\n"
        "2;Bad Date;31.02.1980;01.01.2000;4000;0\n"
        "3;Bad Money;01.01.1980;01.01.2000;viel;0\n"
        "1;Duplicate Id;01.01.1981;01.01.2001;4100;zwei\n"
        "4;Short Row;01.01.1982;01.01.2002;4200\n"
        "\n"
    ),
    "missing.csv": "Kennung;Geburtstag;Startdatum;Fixum\nA;1980-01-01;2000-01-01;5000\n",
}


@pytest.fixture(scope="module")
def reports(tmp_path_factory):
    d = tmp_path_factory.mktemp("imp")
    for name, text in FILES.items():
        (d / name).write_text(text, encoding="utf-8")
    out = subprocess.run(
        [NODE, str(HERE / "js_import_runner.js"), *[str(d / n) for n in FILES]],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return d, json.loads(out.stdout)


@pytest.mark.parametrize("name", FILES)
def test_browser_import_matches_server_import(reports, name):
    d, js = reports
    py = read_employees(d / name)
    j = js[name]
    assert sorted(j["missing"]) == sorted(py.missing_fields)
    assert sorted(j["unmapped"]) == sorted(py.unmapped_headers)
    assert j["employees"] == [e.to_json() for e in py.employees]
    assert len(j["warnings"]) == len(py.warnings), (j["warnings"], py.warnings)


def test_messy_file_keeps_good_rows_and_reports_bad_ones(reports):
    d, _ = reports
    rep = read_employees(d / "messy.csv")
    assert [e.name for e in rep.employees] == ["Ok Person", "Short Row"]
    joined = " ".join(rep.warnings)
    assert "Zeile 3" in joined and "Zeile 4" in joined and "Zeile 5" in joined


def test_two_digit_year_is_in_the_past(reports):
    d, _ = reports
    max_muster = read_employees(d / "german.csv").employees[1]
    assert max_muster.birth_date.year == 1990
