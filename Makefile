# Decibench developer Makefile.
#
# These targets are the canonical way to run things locally. If a CI workflow
# diverges from a target here, the CI workflow is wrong.

PY ?= python
PIP ?= pip

.PHONY: help install install-dev install-bridge test test-fast cov lint fmt mypy \
        bridge bridge-build bridge-test release-check clean

help:
	@echo "Decibench developer commands"
	@echo "  make install         Editable install with [dev,all] extras + bridge"
	@echo "  make install-dev     Editable install with [dev] only"
	@echo "  make test            Full test suite with timeout=60"
	@echo "  make test-fast       Smoke tests only (-m 'not slow')"
	@echo "  make cov             Coverage report (HTML in htmlcov/, terminal summary)"
	@echo "  make lint            ruff check + mypy --strict on src"
	@echo "  make fmt             ruff format src tests"
	@echo "  make bridge          Build + test the Node bridge sidecar"
	@echo "  make release-check   Pre-release gate"
	@echo "  make clean           Remove build, cache, coverage artifacts"

install: install-dev install-bridge

install-dev:
	$(PIP) install -e ".[dev,all]"

install-bridge:
	cd bridge_sidecar && npm install

test:
	$(PY) -m pytest -x --timeout=60

test-fast:
	$(PY) -m pytest -x --timeout=30 -m "not slow"

cov:
	$(PY) -m pytest --cov=decibench --cov-report=html --cov-report=term --cov-report=xml

lint:
	$(PY) -m ruff check src tests
	$(PY) -m mypy --strict src

fmt:
	$(PY) -m ruff format src tests

mypy:
	$(PY) -m mypy --strict src

bridge: bridge-build bridge-test

bridge-build:
	cd bridge_sidecar && npm run build

bridge-test:
	cd bridge_sidecar && npm test

release-check:
	@bash scripts/release-check.sh

clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
