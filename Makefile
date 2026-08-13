.PHONY: help install test lint demo demo-check eval eval-check verify

help:
	@echo "install     Create .venv and install the package with dev extras"
	@echo "test        Run the test suite"
	@echo "lint        Run ruff"
	@echo "demo        Regenerate demo/output/ from unmodified upstream Nav2 files"
	@echo "demo-check  Verify committed demo output still reproduces byte-for-byte"
	@echo "eval        Run the Phase 3 adversarial mutation evaluation"
	@echo "eval-check  Verify committed eval results still reproduce"
	@echo "verify      install + test + demo-check + eval-check (what a reviewer should run)"

VENV := .venv
PY := $(VENV)/bin/python

$(VENV):
	python3 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip --quiet
	$(PY) -m pip install -e ".[dev]" --quiet

install: $(VENV)

test: $(VENV)
	$(PY) -m pytest

lint: $(VENV)
	$(VENV)/bin/ruff check src tests

demo: $(VENV)
	$(PY) scripts/run_demo.py

demo-check: $(VENV)
	$(PY) scripts/run_demo.py --check

eval: $(VENV)
	$(PY) eval/run_eval.py

eval-check: $(VENV)
	$(PY) eval/run_eval.py --check

verify: install test demo-check eval-check
