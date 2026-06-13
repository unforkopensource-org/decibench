"""Tests for Decibench Score calculator.

Uses ``from __future__ import annotations`` for cleaner type hints.
"""

from __future__ import annotations

import pytest

from decibench.config import ScoringWeights
from decibench.evaluators.score import DecibenchScorer
from decibench.models import EvalResult, MetricResult


def _make_result(**metrics: tuple[float, str, bool]) -> EvalResult:
    """Helper to create EvalResult with specific metrics."""
    return EvalResult(
        scenario_id="test",
        passed=True,
        score=0.0,
        metrics={
            name: MetricResult(name=name, value=val, unit=unit, passed=passed)
            for name, (val, unit, passed) in metrics.items()
        },
    )


def test_scorer_empty_results():
    scorer = DecibenchScorer()
    score, breakdown = scorer.calculate([], ScoringWeights(), has_judge=False)
    assert score == 0.0
    assert breakdown == {}


def test_scorer_perfect_metrics():
    scorer = DecibenchScorer()
    result = _make_result(
        turn_latency_p50_ms=(200, "ms", True),
        turn_latency_p95_ms=(400, "ms", True),
        wer=(0.0, "%", True),
        mos_ovrl=(5.0, "/5.0", True),
        task_completion=(100.0, "%", True),
        compliance_score=(100.0, "%", True),
    )
    score, breakdown = scorer.calculate([result], ScoringWeights(), has_judge=True)
    assert score > 80  # Should be high with perfect metrics
    assert "latency" in breakdown
    assert "compliance" in breakdown


def test_scorer_bad_latency():
    scorer = DecibenchScorer()
    result = _make_result(
        turn_latency_p50_ms=(2000, "ms", False),
        turn_latency_p95_ms=(5000, "ms", False),
        wer=(0.0, "%", True),
        mos_ovrl=(4.5, "/5.0", True),
        task_completion=(100.0, "%", True),
        compliance_score=(100.0, "%", True),
    )
    score, breakdown = scorer.calculate([result], ScoringWeights(), has_judge=True)
    # Should be lower due to bad latency
    assert score < 80
    assert breakdown["latency"] < 50  # Bad latency should score low


def test_scorer_no_judge_mode():
    scorer = DecibenchScorer()
    result = _make_result(
        turn_latency_p50_ms=(500, "ms", True),
        wer=(5.0, "%", True),
        mos_ovrl=(4.2, "/5.0", True),
        compliance_score=(100.0, "%", True),
    )
    score, _breakdown = scorer.calculate([result], ScoringWeights(), has_judge=False)
    assert 0 <= score <= 100


def test_scorer_compliance_failure():
    scorer = DecibenchScorer()
    result = _make_result(
        turn_latency_p50_ms=(500, "ms", True),
        wer=(3.0, "%", True),
        mos_ovrl=(4.5, "/5.0", True),
        task_completion=(95.0, "%", True),
        compliance_score=(0.0, "%", False),
        pii_violations=(2.0, "count", False),
    )
    score, _breakdown = scorer.calculate([result], ScoringWeights(), has_judge=True)
    # Compliance failure should impact score
    assert score < 90


def test_intelligibility_curve_exact():
    """intelligibility_estimate normalizer: 0.0->0, 0.45->50, 0.85->100."""
    scorer = DecibenchScorer()
    from decibench.models import EvalResult, MetricResult

    def check(val: float, expected: float) -> None:
        result = EvalResult(
            scenario_id="test",
            passed=True,
            score=0.0,
            metrics={
                "intelligibility_estimate": MetricResult(
                    name="intelligibility_estimate", value=val, unit="", passed=True
                )
            },
        )
        _, breakdown = scorer.calculate([result], ScoringWeights(), has_judge=True)
        assert breakdown.get("audio_quality", 0) == pytest.approx(expected, abs=1), (
            f"value={val} expected={expected}"
        )

    check(0.0, 0.0)
    check(0.45, round(0.45 / 0.85 * 100, 1))
    check(0.85, 100.0)


def test_response_gap_band_scoring():
    """response_gap_avg_ms score matches score_band curve."""
    scorer = DecibenchScorer()
    from decibench.config import LatencyScoringConfig
    from decibench.models import EvalResult, MetricResult

    bands = LatencyScoringConfig()
    result = EvalResult(
        scenario_id="test",
        passed=True,
        score=0.0,
        metrics={
            "response_gap_avg_ms": MetricResult(name="response_gap_avg_ms", value=300, unit="ms", passed=True)
        },
    )
    _, breakdown = scorer.calculate([result], ScoringWeights(), has_judge=True)
    expected = LatencyScoringConfig.score_band(300, bands.response_gap)
    assert breakdown.get("latency", 0) == pytest.approx(expected, abs=1)


def test_turn_gap_band_scoring():
    """turn_gap_avg_ms score matches score_band curve."""
    scorer = DecibenchScorer()
    from decibench.config import LatencyScoringConfig
    from decibench.models import EvalResult, MetricResult

    bands = LatencyScoringConfig()
    result = EvalResult(
        scenario_id="test",
        passed=True,
        score=0.0,
        metrics={"turn_gap_avg_ms": MetricResult(name="turn_gap_avg_ms", value=500, unit="ms", passed=True)},
    )
    _, breakdown = scorer.calculate([result], ScoringWeights(), has_judge=True)
    expected = LatencyScoringConfig.score_band(500, bands.turn_gap)
    assert breakdown.get("robustness", 0) == pytest.approx(expected, abs=1)


def test_scorer_excludes_untested_categories():
    """Untested categories should be excluded, not given free 50."""
    scorer = DecibenchScorer()
    result = _make_result(
        turn_latency_p50_ms=(500, "ms", True),
    )
    _score, breakdown = scorer.calculate([result], ScoringWeights(), has_judge=True)
    # Only latency should appear — untested categories are excluded
    assert "latency" in breakdown
    assert "task_completion" not in breakdown
    assert "compliance" not in breakdown
