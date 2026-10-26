#!/usr/bin/env python3
"""PostToolUse hook (Write|Edit|MultiEdit): run the tests that guard what was just touched.

Feedback goes straight back to the agent (exit 2), so a drift between the
Python engine, the JS engine and the Excel formulas is caught on the edit
that caused it, not three steps later.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TARGETS = {
    "planwerk/engine.py": ["tests/test_engine.py", "tests/test_js_parity.py"],
    "planwerk/model.py": ["tests/test_engine.py", "tests/test_js_parity.py"],
    "web/engine.js": ["tests/test_js_parity.py"],
    "planwerk/excel.py": ["tests/test_import.py", "tests/test_js_import.py", "tests/test_excel_parity.py"],
    "web/importer.js": ["tests/test_js_import.py"],
    "web/index.html": ["tests/test_browser.py"],
    "planwerk/cli.py": ["tests/test_cli.py"],
    "planwerk/paths.py": ["tests/test_api_mcp.py", "tests/test_cli.py"],
    "planwerk/privacy.py": ["tests/test_privacy.py", "tests/test_assistant.py"],
    "planwerk/assistant.py": ["tests/test_assistant.py"],
    "planwerk/api.py": ["tests/test_api_mcp.py"],
    "planwerk/mcp_server.py": ["tests/test_api_mcp.py"],
}


def main() -> None:
    path = json.load(sys.stdin).get("tool_input", {}).get("file_path", "")
    try:
        rel = str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        sys.exit(0)
    tests = TARGETS.get(rel)
    if not tests and rel.startswith("tests/") and rel.endswith(".py"):
        tests = [rel]
    if not tests:
        sys.exit(0)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", *tests],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "PLANWERK_AUDIT_FILE": "0"},
    )
    if r.returncode != 0:
        tail = "\n".join(r.stdout.strip().splitlines()[-25:])
        print(f"{rel} broke {', '.join(tests)}:\n{tail}", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
