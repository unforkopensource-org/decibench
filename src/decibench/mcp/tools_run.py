"""MCP tools for running voice agent tests."""

from __future__ import annotations

from decibench.mcp.server import mcp
from decibench.mcp._helpers import get_config, get_store, format_score_breakdown


@mcp.tool()
async def run_test(
    target: str,
    suite: str = "quick",
    mode: str = "deterministic",
) -> str:
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

    # For semantic-local mode, configure Ollama as judge
    if mode == "semantic-local":
        from decibench.providers.judge.ollama import (
            ensure_model,
            is_ollama_running,
            setup_ollama_judge,
        )

        if not is_ollama_running():
            return (
                "Ollama is not running. Start it with:\n"
                "  ollama serve\n\n"
                "Install from: https://ollama.com"
            )

        if not ensure_model(show_progress=False):
            return (
                "Failed to pull the local model. Run manually:\n"
                "  ollama pull llama3.2:3b"
            )

        judge_uri, judge_model, api_key = setup_ollama_judge()
        config.providers.judge = judge_uri
        config.providers.judge_model = judge_model
        config.providers.judge_api_key = api_key

    # For semantic mode, ensure a judge is configured
    elif mode == "semantic" and not config.has_judge:
        return (
            "Semantic mode requires an LLM judge. Set up a provider first:\n"
            "  export GEMINI_API_KEY='your-key'  (cheapest)\n"
            "  export OPENAI_API_KEY='your-key'\n\n"
            "Or use mode='semantic-local' for free local evaluation with Ollama."
        )

    orchestrator = Orchestrator(config)
    result = await orchestrator.run_suite(target=target, suite=suite)

    # Store the result
    store = get_store()
    run_id = store.save_suite_result(result)

    # Format output
    lines = [
        f"## Decibench Score: {result.decibench_score:.1f}/100",
        "",
        format_score_breakdown(result),
        "",
        f"**Suite**: {result.suite} ({result.total_scenarios} scenarios)",
        f"**Target**: {result.target}",
        f"**Passed**: {result.passed}/{result.total_scenarios}",
        f"**Duration**: {result.duration_seconds:.1f}s",
        f"**Run ID**: `{run_id}`",
    ]

    if result.evaluation_mode == "semantic":
        lines.append(f"**Judge**: {result.judge_model}")

    # Top failures
    failed = [r for r in result.results if not r.passed]
    if failed:
        lines.append("")
        lines.append("### Failed Scenarios")
        for r in failed[:5]:
            failed_metrics = [
                f"{m.name}: {m.value}{m.unit}" for m in r.metrics.values() if not m.passed
            ]
            lines.append(f"- **{r.scenario_id}** (score: {r.score:.0f}) — {', '.join(failed_metrics[:3])}")

    return "\n".join(lines)


@mcp.tool()
async def run_quick_test(target: str = "demo") -> str:
    """Run a fast 10-scenario test. Great for a quick health check.

    Uses deterministic mode (free, no API key needed).
    For the built-in demo agent, just call with no arguments.

    Args:
        target: Agent URI (default: "demo" for the built-in demo agent).
    """
    return await run_test(target=target, suite="quick", mode="deterministic")
