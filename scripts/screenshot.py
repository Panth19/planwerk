"""Screenshots of the running app for review and the README.

    planwerk serve &   then   python scripts/screenshot.py [url] [outdir]

Set PLANWERK_FONT_DIR to a folder with literata-latin-opsz-normal.woff2 and
ibm-plex-sans-latin-{400,500,600}-normal.woff2 (from @fontsource) to render the real
typefaces where Google Fonts is not reachable, e.g. in a sandboxed CI runner.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import Page, Route, sync_playwright

FONT_URL = "https://fonts.gstatic.com/planwerk-local/"  # allowed by the page's CSP
FONTS = [
    ("Literata", "200 900", "literata-latin-opsz-normal.woff2"),
    ("IBM Plex Sans", "400", "ibm-plex-sans-latin-400-normal.woff2"),
    ("IBM Plex Sans", "500", "ibm-plex-sans-latin-500-normal.woff2"),
    ("IBM Plex Sans", "600", "ibm-plex-sans-latin-600-normal.woff2"),
]
SHOTS = [("desktop", (1440, 1000), "light"), ("desktop-dark", (1440, 1000), "dark"), ("phone", (400, 860), "light")]


def serve_local_fonts(page: Page, font_dir: Path) -> None:
    css = "".join(
        f"@font-face{{font-family:'{fam}';font-weight:{w};src:url('{FONT_URL}{f}') format('woff2')}}"
        for fam, w, f in FONTS
    )

    def stylesheet(route: Route) -> None:
        route.fulfill(body=css, content_type="text/css")

    def font(route: Route) -> None:
        name = route.request.url.rsplit("/", 1)[1]
        route.fulfill(body=(font_dir / name).read_bytes(), content_type="font/woff2")

    page.route("https://fonts.googleapis.com/**", stylesheet)
    page.route(FONT_URL + "**", font)


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/img")
    out.mkdir(parents=True, exist_ok=True)
    font_dir = os.environ.get("PLANWERK_FONT_DIR")

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--lang=de-DE"])  # date fields in German format
        for name, (width, height), scheme in SHOTS:
            page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=scheme, locale="de-DE")
            errors: list[str] = []
            page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
            if font_dir:
                serve_local_fonts(page, Path(font_dir))
            page.goto(url)
            page.wait_for_selector("#table tbody tr")
            page.wait_for_timeout(600)
            page.screenshot(path=str(out / f"{name}.png"))
            overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
            print(f"{name}: errors={errors} sideways-scroll={overflow}")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
