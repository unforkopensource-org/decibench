"""MCP tools for inspecting and evaluating imported call traces (the failure inbox)."""

from __future__ import annotations

import json

from decibench.mcp._helpers import get_config, get_store
from decibench.mcp.server import mcp


@mcp.tool()
async def list_calls(
    limit: int = 20,
    source: str | None = None,
    since: str | None = None,
) -> str:
    """List imported production call traces.

    These are real user calls imported from external systems (Twilio, Vapi, etc)
    that you can read or run offline evaluations against.

    Args:
        limit: Max traces to return.
        source: Filter by source system (e.g., "twilio", "vapi").
        since: Filter by ISO-8601 imported timestamp.

    Returns:
        JSON-formatted list of call summaries.
    """
    store = get_store()
    traces = store.list_call_traces(limit=limit, source=source, since=since)
    if not traces:
        return "No imported call traces found."
    return json.dumps(traces, indent=2)


@mcp.tool()
async def get_call(call_id: str) -> str:
    """Get the full transcript and spans for a specific call trace.

    Args:
        call_id: The ID of the call trace.

    Returns:
        The full call trace in JSON format.
    """
    store = get_store()
    trace = store.get_call_trace(call_id)
    if not trace:
        return f"Call trace '{call_id}' not found."
    return trace.model_dump_json(indent=2)


@mcp.tool()
async def evaluate_call(call_id: str, mode: str = "deterministic") -> str:
    """Run an evaluation against a stored call trace.

    This takes an existing conversation and scores it using Decibench's evaluators,
    saving the result to the failure inbox.

    Args:
        call_id: The ID of the call trace to evaluate.
        mode: The evaluation mode ("deterministic" or "semantic").

    Returns:
        Evaluation results summary.
    """
    from decibench.evaluators.core import evaluate_trace
    from decibench.models import Scenario

    store = get_store()
    trace = store.get_call_trace(call_id)
    if not trace:
        return f"Call trace '{call_id}' not found."

    config = get_config()

    if mode == "semantic":
        if not config.has_judge:
            return "Semantic mode requires an LLM judge to be configured."

    # We evaluate against an empty scenario if none is provided,
    # relying on the trace itself for basic metrics like latency.
    # In a real use case, users would match traces to scenarios, but
    # for exploration, this runs the baseline metrics.
    dummy_scenario = Scenario(
        id="imported-trace", description="Evaluation of imported trace", mode="scripted", version=1
    )

    result = await evaluate_trace(trace, dummy_scenario, config)
    eval_id = store.save_call_evaluation(trace, result)

    passed_str = "PASSED" if result.passed else f"FAILED (score: {result.score:.0f})"
    lines = [
        f"Evaluation ID: {eval_id}",
        f"Result: {passed_str}",
        "Failed metrics:" if result.failure_summary else "No failed metrics.",
    ]
    for metric in result.failure_summary:
        lines.append(f"  - {metric}")

    return "\n".join(lines)
