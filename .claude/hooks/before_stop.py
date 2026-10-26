#!/usr/bin/env python3
"""Stop hook: an agent cannot report "done" while the suite is red.

Runs the full suite once. On failure, exit 2 sends the failures back and the
agent keeps working. ``stop_hook_active`` prevents an endless loop when the
agent already tried once and still cannot fix it: then a human decides.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    event = json.load(sys.stdin)
    if event.get("stop_hook_active"):
        sys.exit(0)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True,
                       timeout=600, env={**os.environ, "PLANWERK_AUDIT_FILE": "0"})
    if r.returncode != 0:
        tail = "\n".join(r.stdout.strip().splitlines()[-20:])
        print(f"Not done yet, the test suite is red:\n{tail}", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
