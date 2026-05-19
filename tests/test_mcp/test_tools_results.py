"""Tests for MCP result tools — list_runs, get_run_detail, get_latest_score."""

from __future__ import annotations

from pathlib import Path

import pytest

from decibench.mcp._helpers import get_store
from decibench.mcp.tools_results import get_latest_score, get_run_detail, list_runs
from decibench.models import EvalResult, MetricResult, SuiteResult


@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch, tmp_path: Path):
    """Point the store to a temp database for each test."""
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(tmp_path / "test.sqlite"))
    # Clear the lru_cache so get_store() picks up the new env
    get_store.cache_clear()
    yield
    get_store.cache_clear()


def _make_result(**overrides) -> SuiteResult:
    defaults = dict(
        suite="quick",
        target="demo",
        decibench_score=82.5,
        total_scenarios=10,
        passed=8,
        failed=2,
        evaluation_mode="deterministic",
        score_breakdown={"latency": 90.0, "compliance": 75.0},
        results=[
            EvalResult(
                scenario_id="greeting-001",
                passed=True,
                score=95.0,
                metrics={
                    "ttfw_ms": MetricResult(name="ttfw_ms", value=450.0, unit="ms", passed=True, threshold=800.0),
                },
            ),
            EvalResult(
                scenario_id="compliance-001",
                passed=False,
                score=40.0,
                metrics={
                    "ai_disclosure": MetricResult(name="ai_disclosure", value=0.0, unit="%", passed=False, threshold=100.0),
                },
            ),
        ],
    )
    defaults.update(overrides)
    return SuiteResult(**defaults)


def test_list_runs_empty():
    output = list_runs()
    assert "No test runs found" in output


def test_list_runs_with_data():
    store = get_store()
    store.save_suite_result(_make_result())
    output = list_runs()
    assert "82.5" in output
    assert "quick" in output


def test_list_runs_limit():
    store = get_store()
    for i in range(5):
        store.save_suite_result(_make_result(decibench_score=float(60 + i * 5)))
    output = list_runs(limit=3)
    # Should return at most 3 rows (header + divider + 3 data rows)
    data_rows = [line for line in output.split("\n") if line.startswith("| `")]
    assert len(data_rows) <= 3


def test_get_run_detail_not_found():
    output = get_run_detail("nonexistent-id")
    assert "not found" in output.lower()


def test_get_run_detail_success():
    store = get_store()
    result = _make_result()
    run_id = store.save_suite_result(result)

    output = get_run_detail(run_id)
    assert "82.5" in output
    assert "greeting-001" in output
    assert "compliance-001" in output
    assert "PASS" in output
    assert "FAIL" in output


def test_get_run_detail_prefix_match():
    store = get_store()
    result = _make_result()
    run_id = store.save_suite_result(result)

    # Use first 10 chars as prefix
    prefix = run_id[:10]
    output = get_run_detail(prefix)
    # Should find the run via prefix match
    assert "82.5" in output or "Multiple runs" in output


def test_get_latest_score_empty():
    output = get_latest_score()
    assert "No test runs found" in output


def test_get_latest_score_success():
    store = get_store()
    store.save_suite_result(_make_result(decibench_score=91.3))
    output = get_latest_score()
    assert "91.3" in output
    assert "quick" in output
