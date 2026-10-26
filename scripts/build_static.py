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
    shutil.copy(ROOT / "web" / "engine.js", DIST / "engine.js")
    shutil.copy(ROOT / "data" / "sample_case.json", DIST / "sample_case.json")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    (DIST / "index.html").write_text(html, encoding="utf-8")
    if "--fragment" in sys.argv:
        head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
        body = re.search(r"<body>(.*?)</body>", html, re.S).group(1)
        head = re.sub(r'<meta charset="utf-8">\s*|<meta name="viewport"[^>]*>\s*', "", head)
        (DIST / "fragment.html").write_text(head.strip() + "\n" + body.strip() + "\n", encoding="utf-8")
    print("built", ", ".join(sorted(p.name for p in DIST.iterdir())))


if __name__ == "__main__":
    main()
