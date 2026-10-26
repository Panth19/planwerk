"""Build the browser-only demo (no server, no AI) for static hosting.

    python scripts/build_static.py            # -> dist/  (GitHub Pages, any static host)
    python scripts/build_static.py --fragment # -> dist/fragment.html without <html>/<head>/<body>,
                                              #    for hosts that wrap the page themselves

Everything runs in the visitor's browser; imported lists never leave it.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def main() -> None:
    DIST.mkdir(exist_ok=True)
    for js in ("engine.js", "importer.js"):
        shutil.copy(ROOT / "web" / js, DIST / js)
    shutil.copy(ROOT / "data" / "sample_case.json", DIST / "sample_case.json")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    # No server behind a static host: skip the health probe instead of logging a 404.
    html = html.replace(
        '<script src="engine.js"></script>',
        '<script>window.PLANWERK_STATIC = true;</script>\n<script src="engine.js"></script>',
        1,
    )
    (DIST / "index.html").write_text(html, encoding="utf-8")
    if "--fragment" in sys.argv:
        head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
        body = re.search(r"<body>(.*?)</body>", html, re.S).group(1)
        head = re.sub(r'<meta charset="utf-8">\s*|<meta name="viewport"[^>]*>\s*|<link rel="icon"[^>]*>\s*', "", head)
        (DIST / "fragment.html").write_text(head.strip() + "\n" + body.strip() + "\n", encoding="utf-8")
    print("built", ", ".join(sorted(p.name for p in DIST.iterdir())))


if __name__ == "__main__":
    main()
