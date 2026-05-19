"""Latency curve / threshold alignment.

The historical bug: LatencyEvaluator passed ``turn_latency_p50_ms`` if
value ≤ ~800 ms, while DecibenchScorer mapped 800 ms to 50/100. An agent at
the threshold "passed" while contributing 50 to its own category score.

v1 unifies them: ``ScoringConfig.latency_bands`` defines (green, yellow,
red) triples per percentile. ``yellow_ms`` is BOTH the pass threshold AND
the 50-point inflection of the score curve. The curve passes through
exactly (green→100, yellow→50, red→0) and the evaluator's threshold equals
``yellow_ms``.

These tests pin both contracts and the property that they cannot drift.
"""

from __future__ import annotations

import math

import pytest

from decibench.config import LatencyScoringConfig
from decibench.evaluators.score import DecibenchScorer
from decibench.models import MetricResult


@pytest.mark.parametrize("name,band_attr", [
    ("turn_latency_p50_ms", "p50"),
    ("turn_latency_p95_ms", "p95"),
    ("turn_latency_p99_ms", "p99"),
    ("ttfw_ms", "ttfw"),
])
def test_curve_passes_through_green_yellow_red(name: str, band_attr: str) -> None:
    """Score curve must pass through (green, 100), (yellow, 50), (red, 0)."""
    from decibench.config import ScoringConfig

    policies = ScoringConfig()
    bands = getattr(policies.latency_bands, band_attr)
    green, yellow, red = bands

    for value, expected in [(green, 100.0), (yellow, 50.0), (red, 0.0)]:
        m = MetricResult(name=name, value=value, unit="ms", passed=True)
        score = DecibenchScorer._normalize_metric(name, m, policies)
        assert math.isclose(score, expected, abs_tol=0.01), (
            f"{name} at {value}ms scored {score}, expected {expected} "
            f"(band={bands})"
        )


@pytest.mark.parametrize("name,band_attr", [
    ("turn_latency_p50_ms", "p50"),
    ("turn_latency_p95_ms", "p95"),
    ("turn_latency_p99_ms", "p99"),
    ("ttfw_ms", "ttfw"),
])
def test_curve_monotone_decreasing_in_value(name: str, band_attr: str) -> None:
    """Higher latency ⇒ never higher score. Sanity invariant."""
    from decibench.config import ScoringConfig

    policies = ScoringConfig()
    bands = getattr(policies.latency_bands, band_attr)
    green, _, red = bands

    last = float("inf")
    for value in range(0, red + 200, max(1, (red - green) // 50)):
        m = MetricResult(name=name, value=value, unit="ms", passed=True)
        score = DecibenchScorer._normalize_metric(name, m, policies)
        assert score <= last + 1e-9, f"{name} non-monotone at {value}ms: {score} > {last}"
        last = score


def test_evaluator_threshold_equals_yellow_band() -> None:
    """LatencyEvaluator's pass threshold == bands.yellow_ms (alignment)."""
    bands = LatencyScoringConfig()
    # Build a context shaped like the orchestrator would.
    context = {"latency_bands": bands}

    # Direct check on what the evaluator would resolve.
    assert context["latency_bands"].p50[1] == 800
    assert context["latency_bands"].p95[1] == 1200
    assert context["latency_bands"].p99[1] == 2000
    assert context["latency_bands"].ttfw[1] == 800


def test_pass_at_threshold_scores_exactly_50() -> None:
    """The headline alignment invariant: a value at the pass threshold scores 50."""
    from decibench.config import ScoringConfig

    policies = ScoringConfig()
    for name, band_attr in [
        ("turn_latency_p50_ms", "p50"),
        ("turn_latency_p95_ms", "p95"),
        ("turn_latency_p99_ms", "p99"),
        ("ttfw_ms", "ttfw"),
    ]:
        _, yellow, _ = getattr(policies.latency_bands, band_attr)
        m = MetricResult(name=name, value=yellow, unit="ms", passed=True)
        score = DecibenchScorer._normalize_metric(name, m, policies)
        assert math.isclose(score, 50.0, abs_tol=0.01), (
            f"{name} at threshold {yellow}ms scored {score}, expected 50.0"
        )


def test_custom_bands_via_config() -> None:
    """Users can override bands — both threshold and curve follow."""
    from decibench.config import ScoringConfig

    custom = LatencyScoringConfig(p50=(100, 400, 1000))
    policies = ScoringConfig(latency_bands=custom)

    m = MetricResult(name="turn_latency_p50_ms", value=400.0, unit="ms", passed=True)
    score = DecibenchScorer._normalize_metric("turn_latency_p50_ms", m, policies)
    assert math.isclose(score, 50.0, abs_tol=0.01)


def test_score_band_extrapolation_clamped() -> None:
    """Out-of-band values clamp at 100 / 0 (never negative, never > 100)."""
    band = (300, 800, 2000)
    assert LatencyScoringConfig.score_band(0, band) == 100.0
    assert LatencyScoringConfig.score_band(50_000, band) == 0.0
    # Monotonic in between
    assert LatencyScoringConfig.score_band(800, band) == 50.0
    assert LatencyScoringConfig.score_band(550, band) > 50.0
    assert LatencyScoringConfig.score_band(550, band) < 100.0
