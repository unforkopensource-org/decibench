"""config_hash redaction + suite_version regression tests.

Pins the v1 trust invariants:

1. ``config_hash`` is computed against a secret-redacted view of the config,
   so two engineers with the same scoring config but different API keys
   produce the same hash.
2. ``SuiteResult.suite_version`` carries a stamp from the built-in suite's
   ``suite.toml`` so historical comparisons across suite edits surface.
"""

from __future__ import annotations

from decibench.config import DecibenchConfig
from decibench.models import SuiteResult
from decibench.scenarios.loader import ScenarioLoader


def test_redacted_dump_replaces_api_keys() -> None:
    config = DecibenchConfig.defaults()
    config.auth.openai_api_key = "sk-secret-xyz"
    config.auth.anthropic_api_key = ""
    dump = config.redacted_dump()
    assert dump["auth"]["openai_api_key"] == "<set>"
    assert dump["auth"]["anthropic_api_key"] == "<unset>"
    assert "sk-secret-xyz" not in str(dump)


def test_config_hash_stable_across_different_secrets() -> None:
    """The headline reproducibility property."""
    config_a = DecibenchConfig.defaults()
    config_a.auth.openai_api_key = "sk-engineer-alice"

    config_b = DecibenchConfig.defaults()
    config_b.auth.openai_api_key = "sk-engineer-bob"

    hash_a = SuiteResult.compute_config_hash(config_a.redacted_dump())
    hash_b = SuiteResult.compute_config_hash(config_b.redacted_dump())
    assert hash_a == hash_b, "redacted hashes must match across different API keys"


def test_config_hash_changes_on_scoring_weight_change() -> None:
    """Non-secret changes still move the hash — redaction must not over-collapse."""
    config_a = DecibenchConfig.defaults()
    config_b = DecibenchConfig.defaults()
    config_b.scoring.weights.task_completion = 0.30
    config_b.scoring.weights.latency = 0.15

    hash_a = SuiteResult.compute_config_hash(config_a.redacted_dump())
    hash_b = SuiteResult.compute_config_hash(config_b.redacted_dump())
    assert hash_a != hash_b


def test_suite_version_present_for_builtin_suites() -> None:
    loader = ScenarioLoader()
    for suite in ("quick", "standard", "acoustic", "adversarial"):
        assert loader.suite_version(suite) == "1.0.0", f"missing suite_version for {suite}"


def test_suite_version_for_full_rolls_up_sub_suites() -> None:
    loader = ScenarioLoader()
    stamp = loader.suite_version("full")
    assert "quick=1.0.0" in stamp
    assert "standard=1.0.0" in stamp


def test_suite_version_unknown_suite_returns_empty() -> None:
    loader = ScenarioLoader()
    assert loader.suite_version("nonexistent-suite") == ""


def test_suite_result_carries_suite_version_field() -> None:
    sr = SuiteResult(
        suite="quick",
        target="demo",
        decibench_score=0.0,
        total_scenarios=0,
        passed=0,
        failed=0,
        suite_version="1.0.0",
    )
    assert sr.suite_version == "1.0.0"
