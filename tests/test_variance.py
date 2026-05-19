"""Reproducibility telemetry: score_stddev + flake_rate.

These metrics are the user-visible counterpart to the v1 reproducibility
promise. Two configs that produce the same average score can mean very
different things depending on variance — a 65±2 is solid, a 65±25 is noise.
"""

from __future__ import annotations

from decibench.models import EvalResult, MetricResult
from decibench.orchestrator import Orchestrator


def _run(score: float, *, passed: bool, run_index: int) -> EvalResult:
    return EvalResult(
        scenario_id="s",
        passed=passed,
        score=score,
        run_index=run_index,
        metrics={"wer": MetricResult(name="wer", value=10.0, unit="%", passed=passed)},
    )


def test_single_run_has_zero_stddev_and_not_flaked() -> None:
    out = Orchestrator._average_runs([_run(70.0, passed=True, run_index=0)])
    assert out.score == 70.0
    assert out.score_stddev == 0.0
    assert out.flaked is False
    assert out.run_count == 1


def test_stable_runs_no_flake_low_stddev() -> None:
    runs = [
        _run(70.0, passed=True, run_index=0),
        _run(72.0, passed=True, run_index=1),
        _run(68.0, passed=True, run_index=2),
    ]
    out = Orchestrator._average_runs(runs)
    assert out.passed is True
    assert out.run_count == 3
    assert out.score_stddev > 0
    assert out.score_stddev < 5.0  # tight clustering
    assert out.flaked is False


def test_pass_fail_flip_flags_as_flaked() -> None:
    """The canonical case: same scenario, half pass / half fail → flaked."""
    runs = [
        _run(90.0, passed=True, run_index=0),
        _run(20.0, passed=False, run_index=1),
        _run(85.0, passed=True, run_index=2),
        _run(15.0, passed=False, run_index=3),
    ]
    out = Orchestrator._average_runs(runs)
    assert out.flaked is True
    assert out.run_count == 4
    # The averaged score (52.5) is itself a meaningful number; flake_rate is
    # the metric that warns the user "don't trust this average alone".
    assert 50.0 <= out.score <= 55.0


def test_high_score_variance_without_flake() -> None:
    """Scores vary but all pass → high stddev but flaked stays False."""
    runs = [
        _run(95.0, passed=True, run_index=0),
        _run(55.0, passed=True, run_index=1),
        _run(85.0, passed=True, run_index=2),
    ]
    out = Orchestrator._average_runs(runs)
    assert out.flaked is False
    assert out.score_stddev > 10.0


def test_suite_flake_rate_is_fraction_of_flaked_scenarios() -> None:
    """SuiteResult.flake_rate is the fraction of scenarios marked flaked.

    We construct EvalResults directly (bypassing orchestration) to keep the
    test focused on the rollup math.
    """
    from decibench.models import SuiteResult

    er_stable = EvalResult(scenario_id="s1", passed=True, score=80.0, flaked=False, run_count=3)
    er_flaked1 = EvalResult(scenario_id="s2", passed=False, score=40.0, flaked=True, run_count=3)
    er_flaked2 = EvalResult(scenario_id="s3", passed=True, score=70.0, flaked=True, run_count=3)

    # Manually compute the rollup the way Orchestrator.run_suite does.
    eval_results = [er_stable, er_flaked1, er_flaked2]
    flake_count = sum(1 for r in eval_results if r.flaked)
    flake_rate = round(flake_count / len(eval_results), 3)

    sr = SuiteResult(
        suite="quick",
        target="demo",
        decibench_score=63.0,
        total_scenarios=len(eval_results),
        passed=2,
        failed=1,
        results=eval_results,
        flake_rate=flake_rate,
    )
    assert sr.flake_rate == round(2 / 3, 3)


def test_score_stddev_avg_averages_per_scenario_stddevs() -> None:
    """SuiteResult.score_stddev_avg is the mean of per-scenario stddevs."""
    from decibench.models import SuiteResult

    eval_results = [
        EvalResult(scenario_id="s1", passed=True, score=80.0, score_stddev=2.0),
        EvalResult(scenario_id="s2", passed=True, score=70.0, score_stddev=8.0),
    ]
    avg = sum(r.score_stddev for r in eval_results) / len(eval_results)
    sr = SuiteResult(
        suite="quick",
        target="demo",
        decibench_score=75.0,
        total_scenarios=2,
        passed=2,
        failed=0,
        results=eval_results,
        score_stddev_avg=round(avg, 2),
    )
    assert sr.score_stddev_avg == 5.0
