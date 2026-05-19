"""Canonical scenario location guard.

The scenarios live in one place: ``src/decibench/scenarios/suites/``. There
was previously a parallel copy at ``scenarios/core/`` at the repository root
— useful for dev grepping but a drift trap (edit one, forget the other, ship
a divergent test corpus).

This file makes the divergence impossible: if a scenario YAML reappears
outside the canonical tree, the test fails with the offending paths.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_ROOT = REPO_ROOT / "src" / "decibench" / "scenarios" / "suites"


def test_canonical_suites_directory_exists() -> None:
    """The canonical tree must exist and be non-empty."""
    assert CANONICAL_ROOT.is_dir(), f"missing canonical scenarios at {CANONICAL_ROOT}"
    yamls = list(CANONICAL_ROOT.rglob("*.yaml"))
    assert yamls, f"no scenario YAMLs under {CANONICAL_ROOT}"


def test_no_scenario_yaml_outside_canonical_tree() -> None:
    """Any ``*.yaml`` that names itself like a scenario must live under the canonical tree.

    Looks for the structural markers of a scenario file (a top-level ``id:``
    starting with the suite prefix conventions) rather than blindly matching
    any YAML — this avoids false positives on config files like
    ``suite.toml.yaml`` or vendored Action YAMLs.
    """
    suspect: list[Path] = []
    skip_dirs = {
        ".venv",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        ".git",
        "htmlcov",
        "dist",
        "build",
        "__pycache__",
    }

    for yaml_path in REPO_ROOT.rglob("*.yaml"):
        # Skip the canonical tree itself
        try:
            yaml_path.relative_to(CANONICAL_ROOT)
            continue
        except ValueError:
            pass
        # Skip vendored / build / cache directories
        if any(part in skip_dirs for part in yaml_path.parts):
            continue
        text = yaml_path.read_text(encoding="utf-8", errors="replace")
        # Scenario IDs follow the pattern "<suite>-<slug>-<NNN>" with the
        # suites we ship: quick, standard, acoustic, adversarial.
        if any(f"id: {prefix}-" in text for prefix in ("quick", "standard", "acoustic", "adversarial")):
            suspect.append(yaml_path)

    assert not suspect, (
        "Scenario-shaped YAML found outside the canonical tree "
        f"({CANONICAL_ROOT}):\n  "
        + "\n  ".join(str(p) for p in suspect)
        + "\n\nMove them under src/decibench/scenarios/suites/, or rename the "
        "id: field if these aren't really decibench scenarios."
    )
