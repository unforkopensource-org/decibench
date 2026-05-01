"""Tests for the metric policy system (blocking/scoring/advisory)."""

from __future__ import annotations

import pytest

from decibench.config import DEFAULT_METRIC_POLICIES, DecibenchConfig, ScoringConfig
from decibench.evaluators.score import DecibenchScorer
from decibench.models import EvalResult, MetricResult


# ---------------------------------------------------------------------------
# Config model tests
# ---------------------------------------------------------------------------

class TestScoringConfig:

    def test_default_policies(self):
        sc = ScoringConfig()
        assert sc.get_policy("pii_violations") == "blocking"
        assert sc.get_policy("ai_disclosure") == "scoring"
        assert sc.get_policy("ttfw_ms") == "scoring"

    def test_user_override(self):
        sc = ScoringConfig(policies={"ai_disclosure": "advisory"})
        assert sc.get_policy("ai_disclosure") == "advisory"
        # Others unchanged
        assert sc.get_policy("pii_violations") == "blocking"

    def test_unknown_metric_defaults_to_scoring(self):
        sc = ScoringConfig()
        assert sc.get_policy("some_future_metric") == "scoring"

    def test_keyword_prefix_handling(self):
        sc = ScoringConfig(policies={"keyword_presence": "advisory"})
        assert sc.get_policy("keyword_presence_t0") == "advisory"
        assert sc.get_policy("keyword_presence_t3") == "advisory"

    def test_resolved_policies_merges(self):
        sc = ScoringConfig(policies={"ai_disclosure": "advisory", "custom_metric": "blocking"})
        resolved = sc.resolved_policies
        assert resolved["ai_disclosure"] == "advisory"
        assert resolved["custom_metric"] == "blocking"
        assert resolved["pii_violations"] == "blocking"  # default

    def test_full_config_with_policies(self):
        config = DecibenchConfig(
            scoring={"weights": {}, "policies": {"ai_disclosure": "advisory"}}
        )
        assert config.scoring.get_policy("ai_disclosure") == "advisory"


# ---------------------------------------------------------------------------
# Scorer tests — the core logic
# ---------------------------------------------------------------------------

def _metric(name: str, value: float, unit: str = "%", passed: bool = True, threshold: float | None = None) -> MetricResult:
    return MetricResult(name=name, value=value, unit=unit, passed=passed, threshold=threshold)


def _make_results_with_compliance_failure() -> list[EvalResult]:
    """Scenarios where ai_disclosure fails but everything else passes."""
    results = []
    for i in range(5):
        results.append(EvalResult(
            scenario_id=f"s{i}",
            passed=True,
            score=80.0,
            metrics={
                "ttfw_ms": _metric("ttfw_ms", 400.0, "ms", passed=True, threshold=800.0),
                "ai_disclosure": _metric("ai_disclosure", 0.0, "%", passed=False, threshold=100.0),
                "compliance_score": _metric("compliance_score", 0.0, "%", passed=False, threshold=100.0),
                "task_completion": _metric("task_completion", 95.0, "%", passed=True, threshold=90.0),
            },
        ))
    return results


class TestScorerPolicies:
    scorer = DecibenchScorer()
    weights = DecibenchConfig.defaults().scoring.weights

    def test_no_policies_legacy_behavior(self):
        """Without policies param, scorer behaves like before (compliance cap applies)."""
        results = _make_results_with_compliance_failure()
        score, _ = self.scorer.calculate(results, self.weights, has_judge=False, policies=None)
        # Compliance = 0 triggers hard cap at 30
        assert score <= 30.0

    def test_default_policies_no_cap(self):
        """With default policies, ai_disclosure is 'scoring' not 'blocking',
        so the compliance hard cap should NOT trigger."""
        results = _make_results_with_compliance_failure()
        policies = ScoringConfig()  # default policies
        score, _ = self.scorer.calculate(results, self.weights, has_judge=False, policies=policies)
        # Score should be above 30 because no blocking metric failed
        assert score > 30.0

    def test_blocking_compliance_triggers_cap(self):
        """If ai_disclosure is set to blocking, cap should trigger."""
        results = _make_results_with_compliance_failure()
        policies = ScoringConfig(policies={"ai_disclosure": "blocking"})
        score, _ = self.scorer.calculate(results, self.weights, has_judge=False, policies=policies)
        assert score <= 30.0

    def test_advisory_excluded_from_score(self):
        """Advisory metrics should not affect the score at all."""
        # Scenario where ai_disclosure fails
        results = [EvalResult(
            scenario_id="s1",
            passed=True,
            score=0.0,
            metrics={
                "ttfw_ms": _metric("ttfw_ms", 300.0, "ms", passed=True),
                "ai_disclosure": _metric("ai_disclosure", 0.0, "%", passed=False, threshold=100.0),
                "compliance_score": _metric("compliance_score", 0.0, "%", passed=False, threshold=100.0),
            },
        )]

        # With advisory — compliance metrics don't count
        policies_advisory = ScoringConfig(policies={
            "ai_disclosure": "advisory",
            "compliance_score": "advisory",
        })
        score_adv, breakdown_adv = self.scorer.calculate(
            results, self.weights, has_judge=False, policies=policies_advisory
        )

        # With scoring (default) — compliance metrics reduce score
        policies_scoring = ScoringConfig()
        score_scoring, breakdown_scoring = self.scorer.calculate(
            results, self.weights, has_judge=False, policies=policies_scoring
        )

        # Advisory score should be higher (compliance not dragging it down)
        assert score_adv >= score_scoring

    def test_pii_blocking_always_caps(self):
        """PII violations are blocking by default — should cap score."""
        results = [EvalResult(
            scenario_id="s1",
            passed=False,
            score=0.0,
            metrics={
                "pii_violations": _metric("pii_violations", 3.0, "count", passed=False, threshold=0.0),
                "compliance_score": _metric("compliance_score", 0.0, "%", passed=False, threshold=100.0),
                "ttfw_ms": _metric("ttfw_ms", 300.0, "ms", passed=True),
            },
        )]
        policies = ScoringConfig()  # defaults: pii_violations = blocking
        score, _ = self.scorer.calculate(results, self.weights, has_judge=False, policies=policies)
        assert score <= 30.0

    def test_scoring_metrics_reduce_score_but_no_cap(self):
        """Scoring metrics that fail should reduce the score, not cap it."""
        # All pass
        good = [EvalResult(
            scenario_id="s1", passed=True, score=0.0,
            metrics={
                "ttfw_ms": _metric("ttfw_ms", 300.0, "ms", passed=True),
                "wer": _metric("wer", 2.0, "%", passed=True),
            },
        )]
        # WER fails
        bad = [EvalResult(
            scenario_id="s1", passed=True, score=0.0,
            metrics={
                "ttfw_ms": _metric("ttfw_ms", 300.0, "ms", passed=True),
                "wer": _metric("wer", 50.0, "%", passed=False, threshold=10.0),
            },
        )]
        policies = ScoringConfig()
        score_good, _ = self.scorer.calculate(good, self.weights, has_judge=False, policies=policies)
        score_bad, _ = self.scorer.calculate(bad, self.weights, has_judge=False, policies=policies)
        assert score_good > score_bad


# ---------------------------------------------------------------------------
# Orchestrator pass/fail behavior
# ---------------------------------------------------------------------------

class TestOrchestratorPassFail:
    """Test that the orchestrator's pass/fail logic respects policies.

    We test the logic directly rather than running the full orchestrator,
    since the pass/fail determination is a simple policy check.
    """

    def test_blocking_metric_fails_scenario(self):
        """A failing blocking metric should mark the scenario as failed."""
        policies = ScoringConfig(policies={"task_completion": "blocking"})
        metrics = {
            "task_completion": _metric("task_completion", 30.0, "%", passed=False, threshold=90.0),
            "ttfw_ms": _metric("ttfw_ms", 400.0, "ms", passed=True),
        }
        failures = [
            f"{m.name}: {m.value}"
            for m in metrics.values()
            if not m.passed and policies.get_policy(m.name) == "blocking"
        ]
        assert len(failures) == 1
        assert "task_completion" in failures[0]

    def test_scoring_metric_does_not_fail_scenario(self):
        """A failing scoring metric should NOT mark the scenario as failed."""
        policies = ScoringConfig()  # ai_disclosure defaults to "scoring"
        metrics = {
            "ai_disclosure": _metric("ai_disclosure", 0.0, "%", passed=False, threshold=100.0),
            "ttfw_ms": _metric("ttfw_ms", 400.0, "ms", passed=True),
        }
        failures = [
            f"{m.name}: {m.value}"
            for m in metrics.values()
            if not m.passed and policies.get_policy(m.name) == "blocking"
        ]
        assert len(failures) == 0

    def test_advisory_metric_does_not_fail_scenario(self):
        """Advisory metrics should never cause scenario failure."""
        policies = ScoringConfig(policies={"ai_disclosure": "advisory"})
        metrics = {
            "ai_disclosure": _metric("ai_disclosure", 0.0, "%", passed=False, threshold=100.0),
        }
        failures = [
            f"{m.name}: {m.value}"
            for m in metrics.values()
            if not m.passed and policies.get_policy(m.name) == "blocking"
        ]
        assert len(failures) == 0
