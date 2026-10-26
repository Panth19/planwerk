"""Screenshots of the running app for review and the README.

    planwerk serve &   then   python scripts/screenshot.py [url] [outdir]
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
out = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/img")
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch()
    for name, size, scheme in [("desktop", (1440, 1500), "light"), ("desktop-dark", (1440, 1500), "dark"),
                               ("phone", (400, 2400), "light")]:
        pg = b.new_page(viewport={"width": size[0], "height": size[1]}, color_scheme=scheme)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
        pg.goto(url)
        pg.wait_for_selector("#table tbody tr")
        pg.wait_for_timeout(600)
        pg.screenshot(path=str(out / f"{name}.png"), full_page=False)
        overflow = pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        print(name, "errors:", errors, "h-overflow:", overflow)
    b.close()
