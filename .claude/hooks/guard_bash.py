#!/usr/bin/env python3
"""PreToolUse hook (Bash): refuse the few commands that are hard to undo.

* force pushes and history rewrites on main
* uploading files anywhere (curl -F / --data @file / scp / rsync to a host)
* deleting anything outside the working tree (or the tree itself)
* committing while the fast test suite is red
"""

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RULES = [
    (r"git\s+push\b.*(--force|-f\b|--force-with-lease)", "force push: open a PR or ask the human"),
    (r"git\s+(reset\s+--hard|rebase)\b.*\b(main|origin/main)\b", "rewriting main: use scripts/rollback.sh"),
    (r"curl\b.*(\s-F\s|--form|--data(-binary)?\s+@|-T\s)", "uploading a file with curl"),
    (r"\b(scp|rsync)\b.*\S+:\S*", "copying files to another host"),
]


def deletes_outside_repo(cmd: str) -> bool:
    """True if an rm in the command targets anything outside the working tree."""
    try:
        words = shlex.split(cmd)
    except ValueError:
        return "rm " in cmd  # unparseable and deleting: let a human look
    for i, w in enumerate(words):
        if os.path.basename(w) != "rm":
            continue
        for arg in words[i + 1 :]:
            if arg in {"&&", "||", ";", "|"}:
                break
            if arg.startswith("-"):
                continue
            target = Path(os.path.expandvars(os.path.expanduser(arg)))
            target = (target if target.is_absolute() else Path.cwd() / target).resolve()
            if target == ROOT or ROOT not in target.parents:
                return True
    return False


def main() -> None:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    for rx, why in RULES:
        if re.search(rx, cmd):
            print(f"Blocked by guard_bash: {why}.", file=sys.stderr)
            sys.exit(2)
    if deletes_outside_repo(cmd):
        print("Blocked by guard_bash: deleting outside the repository.", file=sys.stderr)
        sys.exit(2)

    if re.search(r"\bgit\s+commit\b", cmd):
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "-m", "not libreoffice"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if r.returncode != 0:
            tail = "\n".join(r.stdout.strip().splitlines()[-15:])
            print(f"Blocked by guard_bash: tests are red, fix before committing.\n{tail}", file=sys.stderr)
            sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
