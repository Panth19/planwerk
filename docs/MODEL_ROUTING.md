# Which model for which job

Routes live in `planwerk/routing.py`. The principle: choose per task by what a wrong answer
costs and how often the task runs, not one model for the whole app.

| Task | Model | Thinking | Effort | Why |
|---|---|---|---|---|
| `header_mapping` | Claude Haiku 5.5 | disabled | low | Runs when an import has columns the synonym list does not know. Sees ~10 header strings, never a row; the answer is a tiny JSON object that is validated against the real headers. Latency and cost matter, depth does not. |
| `scenario_qa` | Claude Sonnet 5.5 | `between_tools` | medium | Multi-step tool use: understand the question, pick changes, call the engine, maybe call it again, explain. Thinking between tool calls is where the value is; the engine does the maths, so there is no need for a top model to "be careful with numbers". |
| `partner_memo` | Claude Opus 5.5 | adaptive | high | Rare (a few times per case), read by a partner, sets the tone of a negotiation. Worth the strongest model and the extra seconds. |

## Model chaining

The assistant is a chain in which the language model is never the last step for a number:

```
question ──► guard (names?) ──► Sonnet plans ──► engine.simulate / fit / compare
                                     ▲                     │
                                     └──── aggregates ◄────┘   (privacy.llm_view + assert_clean)
                                     │
                                     ▼
                              answer quoting engine numbers
```

The memo is a second chain on top: several `compare` results (engine) ➝ Opus writes prose
around numbers it was given, with an instruction to use only those.

## Local route

`PLANWERK_LLM=local` sends every task to an OpenAI-compatible server on our own hardware
(e.g. vLLM on a DGX). Only on that route may the assistant use the `pseudonymized` privacy
level, which adds per-person rows keyed by Personal-Nr. Names still never leave the process.

## What would change the table

- If header mapping starts failing on real client files, move it up to Sonnet before adding
  prompt complexity; it is called rarely enough.
- If scenario questions start needing legal judgement ("is this cap defensible?"), that is
  a different task with a different route, a human in the loop, and its own evaluation set.
