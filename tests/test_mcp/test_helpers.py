"""Tests for MCP helper utilities."""

from __future__ import annotations

from decibench.mcp._helpers import _score_bar, format_score_breakdown, get_config, get_store
from decibench.models import SuiteResult
from decibench.store.sqlite import RunStore


def test_get_store_returns_runstore():
    store = get_store()
    assert isinstance(store, RunStore)


def test_get_store_is_singleton():
    a = get_store()
    b = get_store()
    assert a is b


def test_get_config_returns_config():
    config = get_config()
    # Should return a valid DecibenchConfig regardless of local toml
    assert config.providers.tts == "edge-tts"
    assert hasattr(config, "target")


def test_score_bar_full():
    bar = _score_bar(100.0)
    assert len(bar) == 10
    assert "\u2591" not in bar  # no empty blocks


def test_score_bar_empty():
    bar = _score_bar(0.0)
    assert len(bar) == 10
    assert "\u2588" not in bar  # no filled blocks


def test_score_bar_half():
    bar = _score_bar(50.0)
    assert bar.count("\u2588") == 5
    assert bar.count("\u2591") == 5


def test_format_score_breakdown_empty():
    result = SuiteResult(
        suite="quick",
        target="demo",
        decibench_score=80.0,
        total_scenarios=10,
        passed=8,
        failed=2,
        score_breakdown={},
    )
    output = format_score_breakdown(result)
    assert "No category breakdown" in output


def test_format_score_breakdown_with_data():
    result = SuiteResult(
        suite="quick",
        target="demo",
        decibench_score=85.0,
        total_scenarios=10,
        passed=9,
        failed=1,
        score_breakdown={
            "latency": 90.0,
            "task_completion": 80.0,
            "compliance": 100.0,
        },
    )
    output = format_score_breakdown(result)
    assert "Latency" in output
    assert "Task Completion" in output
    assert "Compliance" in output
    assert "90" in output
    assert "80" in output
    assert "100" in output
