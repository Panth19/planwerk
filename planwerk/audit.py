"""Structured logs and an audit trail that never contain personal data.

Every log line is one JSON object. Calculations are logged by *fingerprint*
(a hash of scheme + employee ids), headcount and totals. Names, birth dates and
salaries are never logged; ``tests/test_privacy.py`` enforces this.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

LOG_DIR = Path(os.environ.get("PLANWERK_LOG_DIR", "logs"))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname.lower(),
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger(name: str = "planwerk") -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(JsonFormatter())
        log.addHandler(h)
        if os.environ.get("PLANWERK_AUDIT_FILE", "1") == "1":
            try:
                LOG_DIR.mkdir(parents=True, exist_ok=True)
                fh = logging.FileHandler(LOG_DIR / "audit.jsonl", encoding="utf-8")
                fh.setFormatter(JsonFormatter())
                log.addHandler(fh)
            except OSError:
                pass  # read-only filesystem: stderr is enough
        log.setLevel(os.environ.get("PLANWERK_LOG_LEVEL", "INFO"))
        log.propagate = False
    return log


def fingerprint(scheme_json: dict[str, Any], employee_ids: list[str]) -> str:
    """Stable id of 'this scheme on this population', safe to log."""
    h = hashlib.sha256()
    h.update(json.dumps(scheme_json, sort_keys=True).encode())
    h.update("|".join(sorted(employee_ids)).encode())
    return h.hexdigest()[:12]


def event(name: str, **fields: Any) -> None:
    get_logger().info(name, extra={"fields": fields})


@contextmanager
def timed(name: str, **fields: Any) -> Iterator[dict[str, Any]]:
    t0 = time.perf_counter()
    extra: dict[str, Any] = {}
    try:
        yield extra
    except Exception as exc:
        get_logger().error(
            name,
            extra={
                "fields": {
                    **fields,
                    **extra,
                    "error": type(exc).__name__,
                    "ms": round((time.perf_counter() - t0) * 1000, 1),
                }
            },
        )
        raise
    get_logger().info(name, extra={"fields": {**fields, **extra, "ms": round((time.perf_counter() - t0) * 1000, 1)}})
