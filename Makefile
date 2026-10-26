# Common tasks. `make help` lists them.
.DEFAULT_GOAL := help
PY ?= python3

help:  ## show this list
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install:  ## install with all extras for development
	$(PY) -m pip install -e ".[dev]"

lint:  ## ruff, formatting, mypy, JS syntax
	ruff check . && ruff format --check . && mypy planwerk
	node --check web/engine.js && node --check web/importer.js

test:  ## full suite (parity tests need node and LibreOffice, browser tests Playwright)
	$(PY) -m pytest -q

quick:  ## fast suite, no LibreOffice and no browser
	$(PY) -m pytest -q -m "not libreoffice and not browser"

serve:  ## web app on http://127.0.0.1:8765
	$(PY) -m planwerk serve

demo:  ## build the static demo into dist/
	$(PY) scripts/build_static.py

screenshots:  ## refresh docs/img (needs a running server)
	$(PY) scripts/screenshot.py

sample:  ## regenerate the synthetic sample case
	$(PY) scripts/make_sample.py

.PHONY: help install lint test quick serve demo screenshots sample
