# How this repo is built with agents

Planwerk is built by several coding agents working in parallel, with a human deciding what
gets merged. This file is the playbook, plus a log of what went wrong and how it was caught.

## Lanes

The work splits along the seams of the system, so that agents rarely touch the same file:

| Lane | Files | Done when |
|---|---|---|
| engine | `planwerk/engine.py`, `planwerk/model.py`, `web/engine.js` | engine + JS parity tests green |
| excel | `planwerk/excel.py` | LibreOffice parity green for all scenarios |
| ai | `planwerk/assistant.py`, `routing.py`, `privacy.py` | assistant + privacy tests green, privacy-auditor clean |
| interfaces | `planwerk/api.py`, `mcp_server.py`, `cli.py` | API/MCP tests green |
| ui | `web/index.html` | screenshots in light, dark and at 400 px reviewed |

Each lane runs in its own git worktree (`git worktree add ../planwerk-<lane> -b <lane>/...`),
so parallel agents never share a working directory.

## Contracts between lanes

Agents in different lanes do not coordinate by talking; they coordinate through tests.

- **The parity tests are the API of the engine lane.** `tests/test_js_parity.py` and
  `tests/test_excel_parity.py` compare every row of 140 people across 6 to 7 scenarios with
  exact equality. An engine change without a matching JS and Excel change cannot go green.
- **The privacy tests are the API of the ai lane.** The interfaces lane may add MCP tools,
  but every result passes `assert_clean`, and `tests/test_assistant.py` checks that nothing
  sent to a model contains a name, birth date or salary.
- **The Sozialplan text is the API of the ui lane.** If the wording changes, the
  legal-rules-reviewer checks it against the engine.

## Order of a typical feature

1. Plan in one session: which lanes, what each must deliver, which test proves it.
   The plan goes into the PR description.
2. Engine lane first, because everything else depends on its numbers. Its PR includes the
   parity test for the new rule before the rule itself.
3. Other lanes in parallel on top of that branch.
4. Review gates before merge: `parity-checker` for any engine change, `legal-rules-reviewer`
   for rule or wording changes, `privacy-auditor` for anything touching data flow.
5. The human merges. Releases go through `/release`, which runs the gates again.

## Model per role

| Role | Model | Why |
|---|---|---|
| Lead (planning, splitting, merging) | Opus | Sees the whole system, makes the calls that are expensive to get wrong |
| Lane workers | Sonnet | Fast and strong enough inside a well-defined lane with tests as the target |
| legal-rules-reviewer | Opus | Reads law-adjacent text; mistakes are costly and rare reviews are cheap |
| parity-checker, privacy-auditor | Sonnet | Mechanical tracing with clear pass/fail |
| release-manager | Haiku | Scripted steps, changelog writing |

## Noticing when an agent is doing nonsense

The signals that have proven useful, roughly in order of how early they show up:

- **It edits a test to make it pass.** Any diff that touches an assertion and the code it
  checks in the same commit gets read line by line. Loosened tolerances are rejected outright.
- **It works outside its lane.** A UI agent touching `engine.js` is wrong even if the change
  is right; the engine lane has to own it.
- **Its explanation does not match its diff.** "Fixed rounding" with a change to date
  arithmetic is a stop.
- **It invents domain facts.** Paragraph numbers, case law, "standard" values. Those go
  through `docs/RULES.md` and the legal-rules-reviewer, never straight into code.
- **Green too fast.** A new rule whose tests passed on the first run probably has tests that
  do not test it. Make it fail once on purpose.

Hooks catch the mechanical part (`after_edit.py` runs the relevant tests after every edit,
`before_stop.py` refuses "done" while the suite is red); the list above is for the rest.

## Incident log

Real issues from building this repo, each caught by a test or hook before it shipped.

| # | What happened | Caught by | Fix |
|---|---|---|---|
| 1 | One employee's amount differed by 1 € between engine and Excel. 24.8333… years × 5,980 € × 0.75 is exactly 111,377.50 €, but binary floating point gives 111,377.4999…; LibreOffice rounded down, the engine up. | Excel parity test, scenario "months" | Both engines snap to 6 decimals before rounding (`clean()`, `ROUND(x,6)`); regression test `test_exact_half_survives_float_noise` |
| 2 | Re-importing our own Excel export silently dropped the "verheiratet" flag for everyone. The header `Verh. (1/0)` did not match any synonym, so the column was ignored and defaulted to false. | Round-trip import test | Header normalisation strips parentheses; unknown headers are reported, never guessed |
| 3 | Python's `sum()` on floats uses compensated summation since 3.12; JavaScript adds naively. Totals could differ in the last bit and break exact parity. | Spotted in review before the JS port | Plain loops in both engines; rule 2 in CLAUDE.md |
| 4 | The assistant crashed after a successful tool call when building its audit log entry (wrong key in the trace). | Assistant tests with a scripted fake model | One-line fix; tests run without network or key |
| 5 | The API accepted `formula: "magic"` and failed later deep in the engine with a 500. | API test for bad input | Validation in `Scheme.__post_init__`; bad input is a 422 with a reason |
| 6 | The data hook blocked edits to its own test file, which contains the forbidden examples it must catch. | Hook tests | Explicit exemption for `tests/test_hooks.py` only |
