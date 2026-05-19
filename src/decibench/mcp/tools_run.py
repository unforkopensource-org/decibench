"""MCP tools for running voice agent tests."""

from __future__ import annotations

from typing import Any

from decibench.mcp._helpers import (
    format_run_result_rich,
    get_config,
    get_store,
    preflight_check,
)
from decibench.mcp.server import mcp


@mcp.tool()
async def run_test(
    target: str,
    suite: str = "quick",
    mode: str = "deterministic",
    cost_cap_usd: float = 0.5,
) -> dict[str, Any]:
    """Run a Decibench test suite against a voice agent.

    This is the core testing tool. It connects to the voice agent, runs
    scenarios (simulated conversations), and scores the agent on latency,
    audio quality, compliance, conversation accuracy, and task completion.

    Args:
        target: Agent URI. Examples:
            - "demo" (built-in demo, no setup needed)
            - "elevenlabs://agent_abc123" (ElevenLabs Conversational AI)
            - "retell://agent_id" (Retell)
            - "vapi://assistant_id" (Vapi)
            - "twilio://localhost:3000/media-stream" (Twilio mock)
            - "ws://localhost:8080/ws" (any WebSocket agent)
            - "http://localhost:3000/agent" (HTTP endpoint)
        suite: Test suite to run:
            - "quick" (10 scenarios, ~30s)
            - "full" (21 scenarios, ~60s)
        mode: Evaluation mode:
            - "deterministic" (free, no API key needed)
            - "semantic" (uses cloud LLM judge, needs API key)
            - "semantic-local" (free, uses Ollama local model)

    Returns:
        Formatted test results with score breakdown and failure analysis.
    """
    from decibench.orchestrator import Orchestrator

    config = get_config()

    # Pre-flight check before we even try to run
    preflight = preflight_check(target, mode, config)
    if not preflight["ok"]:
        return preflight

    # For semantic-local mode, configure Ollama as judge
    if mode == "semantic-local":
        from decibench.providers.judge.ollama import (
            ensure_model,
            is_ollama_running,
            setup_ollama_judge,
        )

        if not is_ollama_running():
            return {
                "ok": False,
                "findings": ["Ollama is not running."],
                "suggested_actions": ["Start it with: ollama serve", "Install from: https://ollama.com"],
            }

        if not ensure_model(show_progress=False):
            return {
                "ok": False,
                "findings": ["Failed to pull the local model."],
                "suggested_actions": ["Run manually: ollama pull llama3.2:3b"],
            }

        judge_uri, judge_model, api_key = setup_ollama_judge()
        config.providers.judge = judge_uri
        config.providers.judge_model = judge_model
        config.providers.judge_api_key = api_key

    orchestrator = Orchestrator(config)
    result = await orchestrator.run_suite(target=target, suite=suite)

    # Store the result
    store = get_store()
    run_id = store.save_suite_result(result)

    # Format output
    return format_run_result_rich(result, run_id)


@mcp.tool()
async def run_quick_test(target: str = "demo") -> dict[str, Any]:
    """Run a fast 10-scenario test. Great for a quick health check.

    Uses deterministic mode (free, no API key needed).
    For the built-in demo agent, just call with no arguments.

    Args:
        target: Agent URI (default: "demo" for the built-in demo agent).
    """
    return await run_test(target=target, suite="quick", mode="deterministic")
