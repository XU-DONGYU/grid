PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
RUFF ?= .venv/bin/ruff
MYPY ?= .venv/bin/mypy
PYTEST ?= .venv/bin/pytest

.PHONY: install dev run test lint format typecheck scan ci

install:
	python3 -m venv .venv || (rm -rf .venv && python3 -m virtualenv .venv)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

dev:
	$(PYTHON) -m uvicorn app:app --reload --host 127.0.0.1 --port 8000

run:
	$(PYTHON) -m uvicorn app:app --host 0.0.0.0 --port 8000

test:
	$(PYTEST) --cov=app --cov=grid_analyzer --cov-report=term-missing

lint:
	$(RUFF) check .

format:
	$(RUFF) format .

typecheck:
	$(MYPY) app.py grid_analyzer

scan:
	$(PYTHON) scripts/scan_secrets.py

ci: lint typecheck test scan
