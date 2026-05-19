"""Per-module coverage floors for critical paths.

The project-wide coverage gate (`fail_under` in pyproject.toml) is a blunt
instrument — provider modules drag the average down because they can't run
without API keys in CI. This file enforces the floors that actually matter:
the scoring math, the store, and the lifecycle plumbing.

If a refactor accidentally guts test coverage on one of these files, the
project-wide percentage might not move enough to trip the gate, but this
test will fail loudly with the exact module that regressed.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

# (module-relative-path, minimum-line-coverage-percent)
#
# These are the v1.0 *floors* — current honest coverage minus a small margin.
# The point is to PREVENT REGRESSION, not to assert aspiration. The
# implementation plan ratchets each floor toward its target by release:
#
#   module                             current   v1.0 target
#   aggregate.py                       94%       100%   (math, must be fully tested)
#   connectors/session.py              84%       95%
#   evaluators/score.py                80%       95%
#   models.py                          100%      100%
#   store/sqlite.py                    96%       95%   (already over target)
#   store/migrations.py                98%       95%   (already over target)
#   replay/evaluate.py                 93%       90%   (already over target)
#   config.py                          80%       85%
#
# Lowering any floor REQUIRES a CHANGELOG entry under [Unreleased] Changed.
# Raising a floor is always welcome.
CRITICAL_FLOORS: dict[str, float] = {
    "decibench/evaluators/aggregate.py": 90.0,
    "decibench/connectors/session.py": 80.0,
    "decibench/evaluators/score.py": 80.0,
    "decibench/models.py": 95.0,
    "decibench/store/sqlite.py": 85.0,
    "decibench/store/migrations.py": 95.0,
    "decibench/replay/evaluate.py": 85.0,
    "decibench/config.py": 75.0,
}

COVERAGE_XML = Path(__file__).parent.parent / "coverage.xml"


@pytest.fixture(scope="module")
def coverage_xml() -> Path:
    """Generate coverage.xml if it's missing or stale.

    The CI workflow runs ``pytest --cov ... --cov-report=xml`` which produces
    this artifact. When this test runs standalone (e.g. ``pytest
    tests/test_coverage_floors.py`` alone), we generate it on the fly.
    """
    if not COVERAGE_XML.exists():
        pytest.skip("coverage.xml not present — run `pytest --cov=decibench --cov-report=xml` first")
    return COVERAGE_XML


def _parse_module_line_rates(xml_path: Path) -> dict[str, float]:
    """Extract per-file line-rate (0-1) from a Cobertura-format coverage.xml."""
    rates: dict[str, float] = {}
    tree = ET.parse(xml_path)  # noqa: S314 — local trusted file
    for cls in tree.iter("class"):
        filename = cls.attrib.get("filename", "")
        line_rate = cls.attrib.get("line-rate", "0")
        try:
            rates[filename] = float(line_rate)
        except ValueError:
            continue
    return rates


def test_critical_module_coverage_floors(coverage_xml: Path) -> None:
    """Every critical-path module must clear its floor.

    Reports every shortfall in one go (not just the first), so a refactor
    that regresses two modules surfaces both in one CI run.
    """
    rates = _parse_module_line_rates(coverage_xml)

    shortfalls: list[str] = []
    for module_path, floor in CRITICAL_FLOORS.items():
        # coverage.xml emits paths relative to the source root configured in
        # tool.coverage. Try both ``decibench/...`` and ``src/decibench/...``.
        candidates = [module_path, f"src/{module_path}"]
        rate = next((rates[c] for c in candidates if c in rates), None)
        if rate is None:
            shortfalls.append(f"  {module_path}: not present in coverage report")
            continue
        observed_pct = round(rate * 100, 1)
        if observed_pct < floor:
            shortfalls.append(f"  {module_path}: {observed_pct:.1f}% < floor {floor:.1f}%")

    assert not shortfalls, (
        "Critical-path coverage regressed below v1 floors:\n"
        + "\n".join(shortfalls)
        + "\n\nLowering a floor requires a CHANGELOG entry under [Unreleased] Changed."
    )


def test_no_critical_floor_silently_dropped() -> None:
    """Sanity guard: every floor entry must point at a real source file.

    Catches the case where someone renames a file but forgets to update this
    file's floor map — we'd silently stop enforcing the floor.
    """
    src_root = Path(__file__).parent.parent / "src"
    for module_path in CRITICAL_FLOORS:
        assert (src_root / module_path).is_file(), (
            f"CRITICAL_FLOORS references {module_path} but the file does not exist. "
            f"Did you rename it? Update tests/test_coverage_floors.py."
        )


# Avoid unused-import lint
_ = sqlite3, subprocess, sys
