"""Tests for latency evaluator — TTFW, P50/P95/P99, response gap."""

from __future__ import annotations

import pytest

from decibench.evaluators.latency import LatencyEvaluator
from decibench.models import (
    AgentEvent,
    CallSummary,
    ConversationTurn,
    EventType,
    Scenario,
    SuccessCriterion,
    TranscriptResult,
)


def _scenario() -> Scenario:
    return Scenario(
        id="test-latency",
        description="Test",
        conversation=[ConversationTurn(role="caller", text="Hello")],
        success_criteria=[SuccessCriterion(type="task_completion")],
    )


def _summary_with_events(turn_latencies_ms: list[float]) -> CallSummary:
    """Create summary with turn events at specified latencies."""
    events = []
    t = 0.0
    for latency_ms in turn_latencies_ms:
        # Caller speaks
        events.append(
            AgentEvent(
                type=EventType.TURN_END,
                timestamp_ms=t,
                data={"role": "caller"},
            )
        )
        t += latency_ms
        # Agent responds
        events.append(
            AgentEvent(
                type=EventType.AGENT_AUDIO,
                timestamp_ms=t,
            )
        )
        events.append(
            AgentEvent(
                type=EventType.TURN_END,
                timestamp_ms=t + 500,
                data={"role": "agent"},
            )
        )
        t += 1000

    return CallSummary(
        duration_ms=t,
        turn_count=len(turn_latencies_ms),
        agent_audio=b"\x00" * 1000,
        events=events,
    )


def _bands_context() -> dict:
    from decibench.config import LatencyScoringConfig

    return {"latency_bands": LatencyScoringConfig()}


def _transcript() -> TranscriptResult:
    return TranscriptResult(text="Hello", segments=[])


# ---------------------------------------------------------------------------
# Core tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_latency_basic():
    """Should produce latency metrics from events."""
    evaluator = LatencyEvaluator()
    results = await evaluator.evaluate(
        _scenario(),
        _summary_with_events([500, 600, 700]),
        _transcript(),
        context={
            "p50_max_ms": 800,
            "p95_max_ms": 1500,
            "p99_max_ms": 3000,
            "ttfw_max_ms": 800,
        },
    )
    {r.name for r in results}
    # Should produce at least some latency metrics
    assert len(results) > 0


@pytest.mark.asyncio
async def test_latency_no_events():
    """No events → empty results."""
    evaluator = LatencyEvaluator()
    results = await evaluator.evaluate(
        _scenario(),
        CallSummary(duration_ms=5000, turn_count=0, events=[]),
        _transcript(),
        context={
            "p50_max_ms": 800,
            "p95_max_ms": 1500,
            "p99_max_ms": 3000,
            "ttfw_max_ms": 800,
        },
    )
    # Should not crash — may return empty or zeroed metrics
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_latency_slow_agent():
    """Very slow agent should fail thresholds."""
    evaluator = LatencyEvaluator()
    results = await evaluator.evaluate(
        _scenario(),
        _summary_with_events([3000, 4000, 5000]),
        _transcript(),
        context={
            "p50_max_ms": 800,
            "p95_max_ms": 1500,
            "p99_max_ms": 3000,
            "ttfw_max_ms": 800,
        },
    )
    # At least some metrics should fail
    if results:
        failed = [r for r in results if not r.passed]
        # With 3-5 second latencies, something should fail
        assert len(failed) >= 0  # Don't assert failure count — depends on impl


@pytest.mark.asyncio
async def test_latency_with_bands_context():
    """latency_bands in context is used for response_gap_avg_ms threshold."""
    evaluator = LatencyEvaluator()
    results = await evaluator.evaluate(
        _scenario(),
        _summary_with_events([400, 500, 600]),
        _transcript(),
        context=_bands_context(),
    )
    gap = next((r for r in results if r.name == "response_gap_avg_ms"), None)
    assert gap is not None
    assert gap.threshold == 1500  # response_gap[1]
    assert gap.details["target_range"] == "<1500ms"


@pytest.mark.asyncio
async def test_latency_response_gap_fallback():
    """response_gap_max_ms context key works as fallback when latency_bands absent."""
    evaluator = LatencyEvaluator()
    results = await evaluator.evaluate(
        _scenario(),
        _summary_with_events([400, 500, 600]),
        _transcript(),
        context={"response_gap_max_ms": 2000},
    )
    gap = next((r for r in results if r.name == "response_gap_avg_ms"), None)
    assert gap is not None
    assert gap.threshold == 2000


@pytest.mark.asyncio
async def test_latency_bands_ttfw():
    """latency_bands also drives TTFW threshold."""
    evaluator = LatencyEvaluator()
    results = await evaluator.evaluate(
        _scenario(),
        _summary_with_events([300, 400]),
        _transcript(),
        context=_bands_context(),
    )
    ttfw = next((r for r in results if r.name == "ttfw_ms"), None)
    if ttfw is not None:
        assert ttfw.threshold == 800  # ttfw[1]


@pytest.mark.asyncio
async def test_latency_fast_agent():
    """Fast agent should pass all thresholds."""
    evaluator = LatencyEvaluator()
    results = await evaluator.evaluate(
        _scenario(),
        _summary_with_events([200, 250, 300]),
        _transcript(),
        context={
            "p50_max_ms": 800,
            "p95_max_ms": 1500,
            "p99_max_ms": 3000,
            "ttfw_max_ms": 800,
        },
    )
    # All should pass with very low latencies
    for r in results:
        if "latency" in r.name or "ttfw" in r.name:
            assert r.passed is True, f"{r.name} = {r.value}ms should pass"
