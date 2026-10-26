---
description: Answer a what-if question about the current Sozialplan with the real engine (MCP tools).
argument-hint: "[question, e.g. Was kostet ein Deckel von 180.000 €?]"
---

Answer this question about the current case: $ARGUMENTS

Use the `planwerk` MCP tools only (`plan_summary`, `simulate`, `fit_budget`, `compare`).
Never calculate amounts yourself. Change only what the question asks about.

Reply in the language of the question:
1. The answer in one sentence, with the number.
2. A small table: current plan vs. the scenario (total, median, eligible, capped people).
3. At most two sentences on which parameter drives the difference.
