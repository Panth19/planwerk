"""Screenshots of the running app for review and the README.

    planwerk serve &   then   python scripts/screenshot.py [url] [outdir]

Set PLANWERK_FONT_DIR to a folder with literata-latin-opsz-normal.woff2 and
ibm-plex-sans-latin-{400,500,600}-normal.woff2 (from @fontsource) to render the real
typefaces where Google Fonts is not reachable, e.g. in a sandboxed CI runner.
"""

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
out = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/img")
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch()
    for name, size, scheme in [
        ("desktop", (1440, 1000), "light"),
        ("desktop-dark", (1440, 1000), "dark"),
        ("phone", (400, 860), "light"),
    ]:
        pg = b.new_page(viewport={"width": size[0], "height": size[1]}, color_scheme=scheme, locale="de-DE")
        errors: list[str] = []
        pg.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
        pg.on("console", lambda m, errors=errors: m.type == "error" and errors.append(m.text))
        font_dir = os.environ.get("PLANWERK_FONT_DIR")
        if font_dir:
            fd = Path(font_dir)
            css = "".join(
                f"@font-face{{font-family:'{fam}';font-weight:{w};src:url('https://fonts.local/{f}') format('woff2')}}"
                for fam, w, f in [
                    ("Literata", "200 900", "literata-latin-opsz-normal.woff2"),
                    ("IBM Plex Sans", "400", "ibm-plex-sans-latin-400-normal.woff2"),
                    ("IBM Plex Sans", "500", "ibm-plex-sans-latin-500-normal.woff2"),
                    ("IBM Plex Sans", "600", "ibm-plex-sans-latin-600-normal.woff2"),
                ]
            )
            pg.route("https://fonts.googleapis.com/**", lambda r, css=css: r.fulfill(body=css, content_type="text/css"))
            pg.route(
                "https://fonts.local/**",
                lambda r, fd=fd: r.fulfill(
                    body=(fd / r.request.url.rsplit("/", 1)[1]).read_bytes(), content_type="font/woff2"
                ),
            )
        pg.goto(url)
        pg.wait_for_selector("#table tbody tr")
        pg.wait_for_timeout(600)
        pg.screenshot(path=str(out / f"{name}.png"), full_page=False)
        overflow = pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        print(name, "errors:", errors, "h-overflow:", overflow)
    b.close()
