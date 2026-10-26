"""Which model, at which thinking level, for which job.

Picked per task, not per app. The reasoning is in docs/MODEL_ROUTING.md;
the short version:

* header_mapping  – tiny, structured, latency-sensitive. Cheapest model,
                    no thinking. Sees column headers only.
* scenario_qa     – multi-step tool use over the engine. Mid model that
                    thinks between tool calls; the engine does the maths.
* partner_memo    – one document a partner will read and sign off on.
                    Strongest model, adaptive thinking, high effort.

Set PLANWERK_LLM=local to send everything to an OpenAI-compatible server
on our own hardware (e.g. vLLM on the DGX). Only then may the assistant use
the "pseudonymized" privacy level.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class Route:
    model: str
    max_tokens: int
    thinking: dict[str, Any] | None
    effort: str | None
    privacy_level: Literal["aggregates", "pseudonymized"] = "aggregates"

    def api_kwargs(self) -> dict[str, Any]:
        kw: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens}
        if self.thinking:
            kw["thinking"] = self.thinking
        if self.effort:
            kw["output_config"] = {"effort": self.effort}
        return kw


CLOUD: dict[str, Route] = {
    "header_mapping": Route("claude-haiku-5-5", 1_024, {"type": "disabled"}, "low"),
    "scenario_qa": Route("claude-sonnet-5-5", 8_000, {"type": "between_tools"}, "medium"),
    "partner_memo": Route("claude-opus-5-5", 32_000, {"type": "adaptive"}, "high"),
}

LOCAL_MODEL = os.environ.get("PLANWERK_LOCAL_MODEL", "qwen3-32b-instruct")
LOCAL: dict[str, Route] = {
    task: Route(LOCAL_MODEL, r.max_tokens, None, None, privacy_level="pseudonymized") for task, r in CLOUD.items()
}


def route(task: str) -> Route:
    table = LOCAL if os.environ.get("PLANWERK_LLM", "cloud") == "local" else CLOUD
    if task not in table:
        raise KeyError(f"no route for task {task!r}; known: {sorted(table)}")
    return table[task]


def is_local() -> bool:
    return os.environ.get("PLANWERK_LLM", "cloud") == "local"
