"""Cross-scenario sample aggregation.

The headline latency number is the most-quoted output of Decibench, so it has
to be a real measurement. Earlier versions averaged per-scenario p95 values,
which is statistically meaningless: mean(median(A), median(B)) is not the
median of A + B.

This module exposes the right primitives:

- ``nearest_rank_percentile`` — single, well-defined percentile algorithm
  matching ``numpy.percentile(..., method="nearest")`` and the way
  Prometheus / HDR Histograms compute quantiles.
- ``merge_latency_samples`` — gathers raw turn-latency samples carried in
  ``MetricResult.details["raw_samples"]`` across every scenario in a suite.
- ``aggregate_latency`` — convenience function that returns the canonical
  ``{p50_ms, p95_ms, p99_ms, sample_count}`` shape consumed by the
  orchestrator's suite-level rollup.

Every function here is pure and side-effect free. The math invariants are
pinned by property tests in ``tests/test_latency_aggregation.py``.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decibench.models import EvalResult

# Metric name that carries the raw per-turn latency vector. Single source of
# truth — the LatencyEvaluator writes here, the aggregator reads here.
RAW_LATENCY_METRIC = "turn_latency_p50_ms"
RAW_SAMPLES_KEY = "raw_samples"


def nearest_rank_percentile(sorted_values: list[float], p: float) -> float:
    """Nearest-rank percentile on an already-sorted, non-empty list.

    Matches the behavior of ``numpy.percentile(method="nearest")``: returns an
    actually-observed sample, correct for any ``N >= 1``, and never invents an
    interpolated value. This is the right choice for latency monitoring,
    because the number you report has to correspond to a real call.

    Args:
        sorted_values: ascending sample list. Must be non-empty.
        p: percentile in ``[0, 100]``.

    Raises:
        ValueError: if ``sorted_values`` is empty or ``p`` is out of range.
    """
    if not sorted_values:
        raise ValueError("nearest_rank_percentile requires at least one sample")
    if not 0 <= p <= 100:
        raise ValueError(f"percentile {p} not in [0, 100]")
    n = len(sorted_values)
    # Standard nearest-rank formula. ceil(p/100 * N) clamped into [1, N].
    rank = max(1, min(n, math.ceil(p / 100.0 * n)))
    return float(sorted_values[rank - 1])


def merge_latency_samples(results: list[EvalResult]) -> list[float]:
    """Collect raw per-turn latencies from every scenario in a suite.

    Reads from ``MetricResult.details["raw_samples"]`` on the canonical
    ``turn_latency_p50_ms`` metric. Scenarios that produced no latency samples
    contribute nothing — they neither inflate nor deflate the merged
    distribution.

    The function never raises on shape drift; it filters out any value that
    can't be coerced to a positive float so a single malformed scenario can't
    poison the merge.
    """
    merged: list[float] = []
    for result in results:
        metric = result.metrics.get(RAW_LATENCY_METRIC)
        if metric is None:
            continue
        raw = metric.details.get(RAW_SAMPLES_KEY) if metric.details else None
        if not isinstance(raw, list):
            continue
        for value in raw:
            try:
                f = float(value)
            except (TypeError, ValueError):
                continue
            if f > 0 and math.isfinite(f):
                merged.append(f)
    return merged


def aggregate_latency(results: list[EvalResult]) -> dict[str, float]:
    """Suite-level latency rollup over the merged sample distribution.

    Returns a dict shaped exactly like the legacy
    ``Orchestrator._aggregate_latency`` output, with one new field:

    - ``p50_ms``: 50th percentile of the merged samples
    - ``p95_ms``: 95th percentile of the merged samples
    - ``p99_ms``: 99th percentile of the merged samples
    - ``sample_count``: total number of per-turn samples that contributed

    Empty input yields zeros; this keeps consumers (dashboard, JSON reporter,
    `runs show`) from having to special-case the no-data path.
    """
    samples = merge_latency_samples(results)
    if not samples:
        return {"p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "sample_count": 0.0}
    sorted_samples = sorted(samples)
    return {
        "p50_ms": round(nearest_rank_percentile(sorted_samples, 50), 1),
        "p95_ms": round(nearest_rank_percentile(sorted_samples, 95), 1),
        "p99_ms": round(nearest_rank_percentile(sorted_samples, 99), 1),
        "sample_count": float(len(samples)),
    }
