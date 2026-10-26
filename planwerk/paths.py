"""Where the web app and the sample case live.

In a checkout (and an editable install) that is the repository root. A
container or any other non-editable install sets ``PLANWERK_HOME`` to the
directory that holds ``web/`` and ``data/`` (the Dockerfile does).
"""

from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.environ.get("PLANWERK_HOME") or Path(__file__).resolve().parents[1])
WEB = HOME / "web"
SAMPLE = HOME / "data" / "sample_case.json"


def sample_path() -> Path:
    if not SAMPLE.exists():
        raise FileNotFoundError(
            f"Sample case not found at {SAMPLE}. Run from a checkout, or set PLANWERK_HOME to the "
            "directory that contains data/sample_case.json."
        )
    return SAMPLE
