PORT ?= 43123
PY ?= python3

.PHONY: install test run demo

install:
	$(PY) -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest

run:
	.venv/bin/python -m handa

demo:
	@test -x .venv/bin/python || $(MAKE) install
	.venv/bin/pip install -q -e ".[dev]"
	.venv/bin/pytest
	HANDA_PORT=$(PORT) .venv/bin/python -m handa
