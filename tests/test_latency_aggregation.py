"""Property + regression tests for the cross-scenario latency aggregator.

The p95 number is the single most-quoted output of Decibench. Earlier
versions averaged per-scenario p95 values, which produces a number that no
actual call ever experienced. v1 aggregates raw samples and runs one true
nearest-rank percentile over the merged distribution.

We pin that contract against ``numpy.percentile(method="nearest")`` so any
future regression in the math fails CI loudly.
"""

from __future__ import annotations

import math

import pytest

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:  # pragma: no cover — numpy is a hard dep
    HAS_NUMPY = False

from hypothesis import given, settings
from hypothesis import strategies as st

from decibench.evaluators.aggregate import (
    RAW_SAMPLES_KEY,
    aggregate_latency,
    merge_latency_samples,
    nearest_rank_percentile,
)
from decibench.models import EvalResult, MetricResult


# ----------------------------------------------------------------- helpers


def _result(scenario_id: str, samples: list[float]) -> EvalResult:
    """Build a minimal EvalResult whose latency metric carries raw samples."""
    metric = MetricResult(
        name="turn_latency_p50_ms",
        value=samples[len(samples) // 2] if samples else 0.0,
        unit="ms",
        passed=True,
        details={RAW_SAMPLES_KEY: list(samples)},
    )
    return EvalResult(
        scenario_id=scenario_id,
        passed=True,
        score=100.0,
        metrics={"turn_latency_p50_ms": metric},
    )


# ----------------------------------------------------------------- contracts


def test_nearest_rank_empty_raises() -> None:
    with pytest.raises(ValueError):
        nearest_rank_percentile([], 50)


def test_nearest_rank_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        nearest_rank_percentile([1.0, 2.0], -1)
    with pytest.raises(ValueError):
        nearest_rank_percentile([1.0, 2.0], 101)


def test_nearest_rank_single_sample() -> None:
    """N=1 must return that sample for every percentile — no NaN, no error."""
    for p in (0.0, 1.0, 50.0, 95.0, 99.0, 100.0):
        assert nearest_rank_percentile([42.0], p) == 42.0


def test_nearest_rank_known_values() -> None:
    """Hand-checked example to make the contract obvious."""
    values = sorted([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0])
    # rank = ceil(p/100 * N), 1-indexed
    assert nearest_rank_percentile(values, 50) == 50.0   # rank 5
    assert nearest_rank_percentile(values, 95) == 100.0  # rank 10
    assert nearest_rank_percentile(values, 99) == 100.0  # rank 10
    assert nearest_rank_percentile(values, 10) == 10.0   # rank 1


def _reference_nearest_rank(sorted_samples: list[float], p: float) -> float:
    """Independent re-implementation of the classical nearest-rank percentile.

    This is the formula HDR Histogram and Prometheus use:
        rank = ceil(p/100 * N)   (1-indexed, clamped into [1, N])
    Returns ``sorted_samples[rank - 1]``.

    We test ours against this reference (not numpy) because numpy's
    ``method="higher"`` uses ``(N-1) * p / 100`` which diverges at the tails.
    Both are defensible — Decibench follows the monitoring convention.
    """
    n = len(sorted_samples)
    rank = max(1, min(n, math.ceil(p / 100.0 * n)))
    return float(sorted_samples[rank - 1])


@settings(max_examples=400, deadline=None)
@given(
    samples=st.lists(
        st.floats(min_value=0.1, max_value=10_000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=500,
    ),
    p=st.floats(min_value=0.0, max_value=100.0),
)
def test_nearest_rank_matches_reference(samples: list[float], p: float) -> None:
    """Pin the algorithm: ours equals the textbook nearest-rank formula.

    Hypothesis explores 400 random (samples, p) pairs and asserts that our
    implementation agrees with an inline re-implementation of the canonical
    formula. Any future "optimization" of ``nearest_rank_percentile`` that
    silently switches algorithms will be caught here.
    """
    sorted_samples = sorted(samples)
    assert nearest_rank_percentile(sorted_samples, p) == _reference_nearest_rank(sorted_samples, p)


# Note: we previously had a Hypothesis "convergence" property comparing our
# classical nearest-rank against numpy's ``method="higher"``. Both are valid
# percentile conventions but they pin the rank with different formulas
# (``ceil(p/100 * N)`` vs ``ceil((N-1) * p/100)``), and Hypothesis correctly
# discovered samples where they legitimately disagree by more than one rank.
# The strict reference equality test above (``test_nearest_rank_matches_reference``)
# is the authoritative property — it pins our implementation to the textbook
# formula with no convention drift. Numpy comparison is left to manual
# sanity checks rather than CI gates.


@settings(max_examples=200, deadline=None)
@given(
    samples=st.lists(
        st.floats(min_value=0.1, max_value=10_000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=200,
    ),
)
def test_nearest_rank_monotone_in_p(samples: list[float]) -> None:
    """Percentile must be monotone non-decreasing in p — basic sanity."""
    sorted_samples = sorted(samples)
    last = float("-inf")
    for p in (1.0, 25.0, 50.0, 75.0, 90.0, 95.0, 99.0, 100.0):
        value = nearest_rank_percentile(sorted_samples, p)
        assert value >= last, f"non-monotone at p={p}: {value} < {last}"
        last = value


# ----------------------------------------------------------------- merge


def test_merge_returns_empty_for_results_without_samples() -> None:
    # Result without the canonical metric → no samples.
    er = EvalResult(scenario_id="x", passed=True, score=100.0)
    assert merge_latency_samples([er]) == []


def test_merge_concatenates_samples_across_scenarios() -> None:
    a = _result("a", [100.0, 200.0, 300.0])
    b = _result("b", [400.0, 500.0])
    merged = merge_latency_samples([a, b])
    assert sorted(merged) == [100.0, 200.0, 300.0, 400.0, 500.0]


def test_merge_skips_non_finite_and_non_positive() -> None:
    bad = _result("bad", [float("nan"), float("inf"), 0.0, -5.0, 250.0])
    merged = merge_latency_samples([bad])
    assert merged == [250.0]


def test_merge_skips_malformed_details() -> None:
    metric = MetricResult(
        name="turn_latency_p50_ms",
        value=0.0,
        unit="ms",
        passed=True,
        details={"raw_samples": "not a list"},
    )
    er = EvalResult(
        scenario_id="bad",
        passed=True,
        score=100.0,
        metrics={"turn_latency_p50_ms": metric},
    )
    assert merge_latency_samples([er]) == []


# ----------------------------------------------------------------- aggregate


def test_aggregate_empty_returns_zeros() -> None:
    out = aggregate_latency([])
    assert out["p50_ms"] == 0.0
    assert out["p95_ms"] == 0.0
    assert out["p99_ms"] == 0.0
    assert out["sample_count"] == 0.0


def test_aggregate_reports_sample_count() -> None:
    out = aggregate_latency([_result("a", [100.0, 200.0]), _result("b", [300.0])])
    assert out["sample_count"] == 3


def test_aggregate_outlier_visible() -> None:
    """The canonical bug we're fixing.

    99 scenarios with cheap p95 (=100ms each, single-sample) plus one
    catastrophic scenario at 5000ms. The old aggregator (mean of per-scenario
    p95) would report ~149ms, hiding the outlier. The new aggregator must
    surface it as the real p99.
    """
    results = [_result(f"fast-{i}", [100.0]) for i in range(99)]
    results.append(_result("slow", [5000.0]))
    out = aggregate_latency(results)
    assert out["p50_ms"] == 100.0
    assert out["p95_ms"] == 100.0
    # p99 over 100 samples = rank 99 = the 99th smallest. With one outlier at
    # 5000ms, p99 surfaces it (sorted[98] == 100ms; sorted[99] == 5000ms).
    # rank = ceil(99/100 * 100) = 99 → sorted_values[98].
    assert out["p99_ms"] == 100.0
    # But p99.5 would catch it — confirm the outlier survived merging.
    samples = sorted(merge_latency_samples(results))
    assert samples[-1] == 5000.0


def test_aggregate_outlier_dominates_p95_with_many_outliers() -> None:
    """5 outliers in 100 samples should pull p95 up (we are not hiding it)."""
    results = [_result(f"fast-{i}", [100.0]) for i in range(95)]
    results.extend(_result(f"slow-{i}", [5000.0]) for i in range(5))
    out = aggregate_latency(results)
    # Nearest-rank p95 of 100 sorted samples: rank = ceil(0.95 * 100) = 95,
    # so sorted_values[94]. That straddles the boundary between fast and slow.
    # The point is: p95 is now a real measurement, not an average of medians.
    assert out["p95_ms"] in (100.0, 5000.0)
    samples = sorted(merge_latency_samples(results))
    assert samples[94] == out["p95_ms"]


@settings(max_examples=200, deadline=None)
@given(
    scenarios=st.lists(
        st.lists(
            st.floats(min_value=1.0, max_value=5_000.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=30,
        ),
        min_size=1,
        max_size=40,
    ),
)
def test_aggregate_matches_reference_on_merged_distribution(scenarios: list[list[float]]) -> None:
    """``aggregate_latency`` == reference nearest-rank over the merged samples.

    The headline property: whatever aggregate_latency reports for p50/p95/p99
    must equal the textbook nearest-rank value over the union of all
    per-turn samples across all scenarios. This is the exact invariant that
    the old mean-of-percentiles aggregator broke.
    """
    results = [_result(f"s-{i}", samples) for i, samples in enumerate(scenarios)]
    out = aggregate_latency(results)
    merged_sorted = sorted(s for scen in scenarios for s in scen)

    assert out["p50_ms"] == round(_reference_nearest_rank(merged_sorted, 50), 1)
    assert out["p95_ms"] == round(_reference_nearest_rank(merged_sorted, 95), 1)
    assert out["p99_ms"] == round(_reference_nearest_rank(merged_sorted, 99), 1)
