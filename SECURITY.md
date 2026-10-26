# Handling client data

A Sozialplan file holds names, dates of birth, salaries, family status and disabilities of
people about to lose their job. Planwerk is built on the assumption that this data is
confidential client data under professional secrecy (§ 203 StGB, § 43a BRAO) and personal
data under the GDPR, including special categories (Art. 9 GDPR: health, via disability).

## Where data may be

| Place | Allowed | Enforced by |
|---|---|---|
| Git repository | synthetic sample only | `.gitignore`, `guard_data.py` hook, CI check that the sample regenerates identically |
| Browser (static demo) | yes, in memory and the visitor's own browser storage | imports are parsed client-side; nothing is uploaded |
| Server process | yes, in memory; temp files deleted after the request | `api.py` uses `TemporaryDirectory` for imports |
| Logs | **never** personal data | `audit.py` logs fingerprints, counts, totals; `tests/test_privacy.py` |
| Cloud language model | aggregates only | `privacy.llm_view`, `privacy.assert_clean` on every payload, question guard, tests |
| Local language model | aggregates, or pseudonymized rows (Personal-Nr., age, tenure, amount) | `routing.py` sets the level per route |
| MCP clients | aggregates and Personal-Nr. | every MCP tool result passes `assert_clean` |

## Working on a real case

1. Keep the case outside the repo, e.g. `~/planwerk-cases/<matter>/`. The agent settings deny
   reading that folder, so an agent session never ingests it by accident.
2. Run `planwerk serve` locally and import the list in the browser, or point the MCP server
   at it with `PLANWERK_CASE=...` for a session that needs it.
3. For the assistant, prefer `PLANWERK_LLM=local`. With the cloud route, it sees aggregates only.
4. Exports go to `out/` (git-ignored). Delete them when the matter is closed.

## Reporting

Found a way data could leave where it should not? Open a private issue or tell the
maintainer directly. Please do not include real data in the report.
