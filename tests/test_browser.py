"""The web app in a real browser, against the real server.

Needs Playwright with Chromium (``pip install playwright && playwright install chromium``);
skipped otherwise. Fonts are stubbed so the test runs offline; SheetJS for the Excel
import is loaded from cdnjs, or from PLANWERK_SHEETJS (a local xlsx.full.min.js) if set.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.browser

PEOPLE_CSV = (
    "Pers.-Nr.;Mitarbeiter;Geb.-Datum;Eintrittsdatum;Monatsbrutto;Kinder\n"
    "4711;Erika Muster;03.04.1971;01.08.1998;4.250,50 €;2\n"
    "4712;Max Muster;12.11.90;31.02.2019;3.980;0\n"
    "4713;Lena Muster;12.11.1990;15.02.2019;3.980;0\n"
)


@pytest.fixture(scope="module")
def server():
    import uvicorn

    from planwerk.api import app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/"
    srv.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browser binary not installed
            pytest.skip(f"Chromium not available: {exc}")
        yield b
        b.close()


@pytest.fixture
def page(browser, server):
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="de-DE", accept_downloads=True)
    ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=server.rstrip("/"))
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(body="", content_type="text/css"))
    sheetjs = os.environ.get("PLANWERK_SHEETJS")
    if sheetjs:
        pg.route(
            "https://cdnjs.cloudflare.com/**",
            lambda r: r.fulfill(body=Path(sheetjs).read_bytes(), content_type="application/javascript"),
        )
    pg.goto(server)
    pg.wait_for_selector("#table tbody tr")
    pg.click('.lang button[data-lang="de"]')
    yield pg
    assert not pg.errors, pg.errors
    ctx.close()


def stored(pg, field):
    return pg.evaluate(f"JSON.parse(localStorage.getItem('planwerk.scheme')).{field}")


def test_opens_with_the_sample_case(page):
    assert page.text_content("#total") == "8.899.233 €"
    assert page.locator("#table tbody tr").count() == 140
    assert page.get_attribute("#f-factor", "aria-label") == "Faktor"


@pytest.mark.parametrize(
    ("field", "typed", "expected"),
    [
        ("factor", "0.8", 0.8),
        ("factor", "0,8", 0.8),
        ("factor", ",5", 0.5),
        ("cap_amount", "150.000", 150000),
        ("cap_amount", "150,000", 150000),
        ("cap_amount", "1.500.000", 1500000),
    ],
)
def test_numbers_are_read_the_way_people_type_them(page, field, typed, expected):
    page.fill(f"#f-{field}", typed)
    assert stored(page, field) == expected


def test_implausible_input_is_marked_and_ignored(page):
    before = page.text_content("#total")
    for field, typed in [("factor", "abc"), ("factor", "25"), ("retirement_age", "63,5")]:
        page.fill(f"#f-{field}", typed)
        assert page.get_attribute(f"#f-{field}", "aria-invalid") == "true"
    assert page.text_content("#total") == before


def test_fit_to_volume_then_reset(page):
    page.click("#pinBtn")
    page.click("#fitBtn")
    assert page.input_value("#f-factor") == "0,524"
    assert page.text_content("#total") == "6.499.346 €"
    assert page.is_visible("#stamp")
    page.click("#resetBtn")
    assert page.text_content("#total") == "8.899.233 €"


def test_copy_table_for_excel(page):
    page.click("#copyBtn")
    clip = page.evaluate("navigator.clipboard.readText()")
    assert clip.startswith("Nr.\tName") and clip.count("\n") == 140


def test_excel_model_round_trip(page, tmp_path):
    with page.expect_download() as dl:
        page.click("#xlsxBtn")
    path = tmp_path / dl.value.suggested_filename
    dl.value.save_as(path)
    assert path.name.startswith("Sozialplan_Anlage1_")
    page.set_input_files("#file", str(path))
    try:  # a locator wait, not wait_for_function: the page's CSP forbids eval
        playwright_api.expect(page.locator("#note")).to_contain_text("importiert", timeout=8000)
    except AssertionError:
        pytest.skip("SheetJS not reachable (" + page.text_content("#note") + "); set PLANWERK_SHEETJS to run offline")
    assert "140 Personen importiert" in page.text_content("#note")


def test_csv_import_keeps_good_rows_and_names_bad_ones(page, tmp_path):
    csv = tmp_path / "liste.csv"
    csv.write_text(PEOPLE_CSV, encoding="utf-8")
    page.set_input_files("#file", str(csv))
    playwright_api.expect(page.locator("#note")).to_contain_text("importiert")
    note = page.text_content("#note")
    assert "2 Personen importiert" in note and "Zeile 3" in note
    assert page.locator("#table tbody tr").count() == 2
    assert "Eigene Daten" in page.text_content("#dataChip")


def test_english(page):
    page.click('.lang button[data-lang="en"]')
    assert page.text_content("#tAnlage") == "Annex 1"
    assert page.get_attribute("#f-cap_amount", "aria-label") == "Maximum amount in euros"


def test_phone_layout(browser, server):
    pg = browser.new_page(viewport={"width": 390, "height": 844}, locale="de-DE")
    pg.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(body="", content_type="text/css"))
    pg.goto(server)
    pg.wait_for_selector("#table tbody tr")
    assert pg.is_visible(".mobilebar") and "€" in pg.text_content("#mbTotal")
    assert not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    pg.close()


def test_stichtag_is_typed_like_in_a_document(page):
    assert page.input_value("#f-stichtag") == "31.12.2026"
    page.fill("#f-stichtag", "30.06.2027")
    assert stored(page, "stichtag") == "2027-06-30"
    page.fill("#f-stichtag", "31.02.2027")
    assert page.get_attribute("#f-stichtag", "aria-invalid") == "true"
    assert stored(page, "stichtag") == "2027-06-30"
