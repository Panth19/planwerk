#!/usr/bin/env python3
"""PreToolUse hook (Write|Edit|MultiEdit): keep client data out of the repo.

Blocks (exit 2, reason goes back to the agent):
  * writing case or employee files anywhere but data/sample_case.json
  * content with IBANs, German tax ids or social security numbers
  * a case file that declares itself non-synthetic
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_DATA = {ROOT / "data" / "sample_case.json"}

PATTERNS = {
    "IBAN": re.compile(r"\bDE\d{2}\s?(?:\d{4}\s?){4}\d{2}\b"),
    "Steuer-ID": re.compile(r"\b(?:Steuer-?ID|IdNr)\D{0,5}\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b", re.I),
    "SV-Nummer": re.compile(r"\b\d{2}\s?\d{6}\s?[A-Z]\s?\d{3}\b"),
}


def block(reason: str) -> None:
    print(f"Blocked by guard_data: {reason}. Real case data lives outside the repo "
          f"(~/planwerk-cases/), see SECURITY.md.", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    event = json.load(sys.stdin)
    tool_input = event.get("tool_input", {})
    path = Path(tool_input.get("file_path", "")).resolve()
    content = tool_input.get("content") or tool_input.get("new_string") or ""
    if isinstance(tool_input.get("edits"), list):
        content += "\n".join(e.get("new_string", "") for e in tool_input["edits"])

    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        sys.exit(0)  # outside the repo: not our business

    if rel.parts and rel.parts[0] in {"cases", "data"} and path not in ALLOWED_DATA:
        block(f"{rel} is a data location; only data/sample_case.json (synthetic) belongs in git")
    if path.suffix.lower() in {".xlsx", ".xlsm", ".csv"} and rel.parts[0] not in {"tests", "docs"}:
        block(f"{rel}: spreadsheets are generated into out/, never committed")
    if rel == Path("tests/test_hooks.py"):
        sys.exit(0)  # holds the bad examples this hook must catch
    for name, rx in PATTERNS.items():
        if rx.search(content):
            block(f"content contains something that looks like a {name}")
    if '"synthetic": false' in content.replace(" ", "").replace('":false', '": false'):
        block("this file declares itself non-synthetic case data")
    sys.exit(0)


if __name__ == "__main__":
    main()
