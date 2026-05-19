#!/usr/bin/env bash
# Decibench release pre-flight.
#
# Runs the most important gates from RELEASE.md in one shot. The full checklist
# in RELEASE.md is the source of truth — this script catches the mechanical
# subset.

set -euo pipefail

cd "$(dirname "$0")/.."

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }

fail=0
ok()   { green "  PASS $*"; }
warn() { yellow "  WARN $*"; }
err()  { red   "  FAIL $*"; fail=1; }

step() { echo; echo "▶ $*"; }

step "Git state"
if [ -n "$(git status --porcelain)" ]; then
  err "working tree has uncommitted changes"
else
  ok "working tree clean"
fi

step "Versions in lock-step"
py_version=$(python -c "import decibench; print(decibench.__version__)")
pyproject_version=$(python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
bridge_version=$(python -c "import json;print(json.load(open('bridge_sidecar/package.json'))['version'])")
echo "  __version__         = $py_version"
echo "  pyproject version    = $pyproject_version"
echo "  bridge package.json  = $bridge_version"
if [ "$py_version" = "$pyproject_version" ] && [ "$py_version" = "$bridge_version" ]; then
  ok "versions match"
else
  err "version drift across Python and bridge"
fi

step "Lint + type-check"
python -m ruff check src tests && ok "ruff clean" || err "ruff issues"
python -m ruff format --check src tests && ok "format clean" || err "format drift"
python -m mypy --strict src && ok "mypy strict clean" || err "mypy issues"

step "Tests + coverage"
python -m pytest --cov=decibench --cov-fail-under=78 -x --timeout=60 \
  && ok "tests + coverage floor" \
  || err "test or coverage gate failed"

step "Docs-truth"
python -m pytest tests/test_docs_truth.py -v && ok "docs-truth invariants" || err "drift"

step "CHANGELOG entry for current version"
if grep -q "^## \[$py_version\]" CHANGELOG.md; then
  ok "CHANGELOG has [$py_version] section"
else
  warn "CHANGELOG.md missing [$py_version] section — required before tagging"
fi

echo
if [ "$fail" -ne 0 ]; then
  red "release-check FAILED"
  exit 1
fi
green "release-check passed"
