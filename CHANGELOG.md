# Changelog

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
