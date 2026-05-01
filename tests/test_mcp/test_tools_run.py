"""Tests for MCP run tools — run_test, run_quick_test."""

from __future__ import annotations

from pathlib import Path

import pytest

from decibench.mcp._helpers import get_store
from decibench.mcp.tools_run import run_test, run_quick_test


@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(tmp_path / "test.sqlite"))
    get_store.cache_clear()
    yield
    get_store.cache_clear()


@pytest.mark.asyncio
async def test_run_test_demo():
    """Run the built-in demo agent — should complete and return a score."""
    output = await run_test(target="demo", suite="quick", mode="deterministic")
    assert "Decibench Score" in output
    assert "Run ID" in output


@pytest.mark.asyncio
async def test_run_quick_test_demo():
    output = await run_quick_test(target="demo")
    assert "Decibench Score" in output


@pytest.mark.asyncio
async def test_run_test_semantic_no_key():
    """Semantic mode without API key should return a helpful error."""
    output = await run_test(target="demo", suite="quick", mode="semantic")
    # Should either run (if key is set) or tell user to set key
    assert "Decibench Score" in output or "Semantic mode requires" in output


@pytest.mark.asyncio
async def test_run_test_stores_result():
    """After a run, the result should be queryable via the store."""
    output = await run_test(target="demo", suite="quick", mode="deterministic")
    assert "Run ID" in output

    store = get_store()
    runs = store.list_runs(limit=1)
    assert len(runs) >= 1
    assert runs[0]["suite"] == "quick"
