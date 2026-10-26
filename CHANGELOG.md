# Changelog

## 1.0.0

First release.

### Fixed
- Client lists: `4.250` in German notation and `4,250.50` in English notation are read
  correctly; two-digit birth years land in the past; impossible dates (31.02.) are rejected
  in the browser as on the server; short rows and broken files report a reason.
- Excel export: client text can no longer become a formula; temp files are removed.
- Uploads work on a fresh install (missing `python-multipart`).
- Typing `0.8` into a German number field gives 0.8, not 8.
- `deploy.sh` resolves tags to commits.

### Added
- Browser import shares one implementation (`web/importer.js`) tested against the server.
- Unknown spreadsheet headers are matched by the small model when one is configured.
- Plausibility checks on every field, a warning when the minimum exceeds the maximum,
  restoring the starting values, a total bar on phones, print layout.
- Security headers with a strict Content Security Policy, upload and input limits,
  502 with a plain message when the model is down, token counts in the audit log.
- `python -m planwerk`, `planwerk memo`, a Makefile, end-to-end browser tests,
  CI on Python 3.11 to 3.13 with ruff and mypy.

## 0.9.0

First version for review.

### Added
- Calculation engine: standard and divisor formula, three tenure rounding modes, minimum
  tenure, Sockelbetrag, Höchstbetrag, rentennahe Jahrgänge, Zuschläge for children and
  Schwerbehinderung, pro-rata cut to a volume, rounding to 1, 10 or 100 €.
- Fitting the factor (in thousandths) or divisor (in tenths) to a volume.
- Sozialauswahl points per person.
- Web app: the Sozialplan as an editable document, cost against volume, saved scenario
  for comparison, chart, Anlage 1 with search, filter and copy to Excel. German and English.
- Excel export with live formulas and named parameters; import of client lists with German
  or English headers, in the browser or on the server.
- MCP server with eight tools, HTTP API, command line.
- Assistant with tool use and model routing; names and personal data never reach a cloud model.
- Hooks, subagents and commands for working with coding agents; CI with GitHub Pages demo;
  container deploy with health check and automatic rollback.
