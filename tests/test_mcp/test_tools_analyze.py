"""Tests for MCP analysis tools — analyze_failures, compare_runs."""

from __future__ import annotations

from pathlib import Path

import pytest

from decibench.mcp._helpers import get_store
from decibench.mcp.tools_analyze import analyze_failures, compare_runs
from decibench.models import EvalResult, MetricResult, SuiteResult


@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(tmp_path / "test.sqlite"))
    get_store.cache_clear()
    yield
    get_store.cache_clear()


def _make_result(**overrides) -> SuiteResult:
    defaults = dict(
        suite="quick",
        target="demo",
        decibench_score=70.0,
        total_scenarios=3,
        passed=1,
        failed=2,
        evaluation_mode="deterministic",
        score_breakdown={"latency": 80.0, "compliance": 60.0},
        results=[
            EvalResult(
                scenario_id="s1",
                passed=True,
                score=90.0,
                metrics={
                    "ttfw_ms": MetricResult(
                        name="ttfw_ms", value=400.0, unit="ms", passed=True, threshold=800.0
                    ),
                },
            ),
            EvalResult(
                scenario_id="s2",
                passed=False,
                score=30.0,
                metrics={
                    "ai_disclosure": MetricResult(
                        name="ai_disclosure", value=0.0, unit="%", passed=False, threshold=100.0
                    ),
                    "task_completion": MetricResult(
                        name="task_completion", value=40.0, unit="%", passed=False, threshold=90.0
                    ),
                },
            ),
            EvalResult(
                scenario_id="s3",
                passed=False,
                score=50.0,
                metrics={
                    "ai_disclosure": MetricResult(
                        name="ai_disclosure", value=0.0, unit="%", passed=False, threshold=100.0
                    ),
                },
            ),
        ],
    )
    defaults.update(overrides)
    return SuiteResult(**defaults)


def test_analyze_failures_no_runs():
    output = analyze_failures()
    assert "No test runs found" in output


def test_analyze_failures_no_failures():
    store = get_store()
    result = SuiteResult(
        suite="quick",
        target="demo",
        decibench_score=100.0,
        total_scenarios=2,
        passed=2,
        failed=0,
        results=[
            EvalResult(
                scenario_id="s1",
                passed=True,
                score=100.0,
                metrics={
                    "ttfw_ms": MetricResult(name="ttfw_ms", value=300.0, unit="ms", passed=True),
                },
            ),
            EvalResult(
                scenario_id="s2",
                passed=True,
                score=100.0,
                metrics={
                    "ttfw_ms": MetricResult(name="ttfw_ms", value=350.0, unit="ms", passed=True),
                },
            ),
        ],
    )
    store.save_suite_result(result)
    output = analyze_failures()
    assert "No failures" in output
    assert "100.0" in output


def test_analyze_failures_with_failures():
    store = get_store()
    run_id = store.save_suite_result(_make_result())
    output = analyze_failures(run_id)
    assert "Failure Analysis" in output
    assert "Ai Disclosure" in output
    # ai_disclosure fails in 2/3 scenarios — should be ranked #1
    assert output.index("Ai Disclosure") < output.index("Task Completion")


def test_analyze_failures_not_found():
    output = analyze_failures("bogus-id")
    assert "not found" in output.lower()


def test_compare_runs_basic():
    store = get_store()
    id_a = store.save_suite_result(_make_result(decibench_score=60.0, timestamp="2025-01-01T00:00:00"))
    id_b = store.save_suite_result(
        _make_result(
            decibench_score=80.0,
            passed=2,
            failed=1,
            score_breakdown={"latency": 90.0, "compliance": 70.0},
            timestamp="2025-01-02T00:00:00",
        )
    )
    output = compare_runs(id_a, id_b)
    assert "Run Comparison" in output
    assert "60.0" in output
    assert "80.0" in output
    assert "improved" in output


def test_compare_runs_not_found():
    output = compare_runs("bad-a", "bad-b")
    assert "not found" in output.lower()


def test_compare_runs_category_changes():
    store = get_store()
    id_a = store.save_suite_result(
        _make_result(
            decibench_score=60.0,
            score_breakdown={"latency": 70.0, "compliance": 50.0},
            timestamp="2025-03-01T00:00:00",
        )
    )
    id_b = store.save_suite_result(
        _make_result(
            decibench_score=80.0,
            score_breakdown={"latency": 90.0, "compliance": 70.0},
            timestamp="2025-03-02T00:00:00",
        )
    )
    output = compare_runs(id_a, id_b)
    assert "Category Changes" in output
    assert "Latency" in output
    assert "Compliance" in output
