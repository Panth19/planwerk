from datetime import date

from planwerk.excel import export_workbook, map_headers, read_employees


def test_roundtrip_through_our_own_export(sample_case, tmp_path):
    path = export_workbook(sample_case, tmp_path / "case.xlsx")
    rep = read_employees(path)
    assert rep.ok, rep.missing_fields
    assert len(rep.employees) == len(sample_case.employees)
    assert rep.employees == sample_case.employees


def test_german_csv_with_client_headers(tmp_path):
    p = tmp_path / "liste.csv"
    p.write_text(
        "Pers.-Nr.;Mitarbeiter;Geb.-Datum;Eintrittsdatum;Monatsbrutto;Kinder;Familienstand;SB\n"
        "4711;Erika Muster;03.04.1971;01.08.1998;4.250,50 €;2;ja;nein\n"
        "4712;Max Muster;12.11.1990;15.02.2019;3.980,00;0;nein;x\n"
        ";Summe;;;;;;\n",
        encoding="utf-8",
    )
    rep = read_employees(p)
    assert rep.ok
    e, f = rep.employees
    assert e.birth_date == date(1971, 4, 3)
    assert e.monthly_gross == 4250.50
    assert e.married and not e.disabled
    assert f.disabled and f.children == 0


def test_unknown_headers_are_reported_not_guessed(tmp_path):
    p = tmp_path / "odd.csv"
    p.write_text("Kennung,Geburtstag,Startdatum Konzern,Fixum\nA,1980-01-01,2000-01-01,5000\n", encoding="utf-8")
    rep = read_employees(p)
    assert not rep.ok
    assert set(rep.missing_fields) == {"birth_date", "entry_date", "monthly_gross"}
    assert "Fixum" in rep.unmapped_headers

    fixed = read_employees(
        p, overrides={"birth_date": "Geburtstag", "entry_date": "Startdatum Konzern", "monthly_gross": "Fixum"}
    )
    assert fixed.ok and fixed.employees[0].monthly_gross == 5000


def test_header_normalisation():
    mapping, unmapped = map_headers(["Brutto-Monatsgehalt", "Geb.-Datum (TT.MM.JJJJ)", "Kommentar"])
    assert mapping["monthly_gross"] == "Brutto-Monatsgehalt"
    assert mapping["birth_date"] == "Geb.-Datum (TT.MM.JJJJ)"
    assert unmapped == ["Kommentar"]


def test_export_never_turns_client_text_into_formulas(sample_case, tmp_path):
    from dataclasses import replace

    from openpyxl import load_workbook

    evil = replace(sample_case.employees[0], id="=1+1", name='=HYPERLINK("http://x","klick")')
    sample_case.employees[0] = evil
    sample_case.title = "=cmd|' /C calc'!A0"
    path = export_workbook(sample_case, tmp_path / "x.xlsx")
    wb = load_workbook(path)
    a = wb["Anlage 1"]
    assert a["A2"].data_type == "s" and a["B2"].data_type == "s"
    assert wb["Parameter"]["A1"].data_type == "s"
    assert a["S2"].data_type == "f"  # our own formulas stay formulas
