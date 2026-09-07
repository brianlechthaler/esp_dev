.PHONY: test lint format

PYTHON ?= python3

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check src tests install.py
	$(PYTHON) -m ruff format --check src tests install.py
	$(PYTHON) -m mypy src

format:
	$(PYTHON) -m ruff check --fix src tests install.py
	$(PYTHON) -m ruff format src tests install.py
