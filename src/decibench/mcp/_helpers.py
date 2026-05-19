"""Shared helpers for Decibench MCP tools."""

from __future__ import annotations

from functools import lru_cache

from typing import Any

from decibench.config import DecibenchConfig, find_config, load_config
from decibench.models import SuiteResult
from decibench.store.sqlite import RunStore


@lru_cache(maxsize=1)
def get_store() -> RunStore:
    """Return a singleton RunStore instance."""
    return RunStore()


def get_config() -> DecibenchConfig:
    """Load the current Decibench configuration.

    Reads from decibench.toml if present, otherwise returns defaults.
    Not cached — config may change between tool calls.
    """
    config_path = find_config()
    return load_config(config_path)


def format_score_breakdown(result: SuiteResult) -> str:
    """Format score breakdown as a markdown table."""
    if not result.score_breakdown:
        return "*No category breakdown available.*"

    lines = [
        "| Category | Score |",
        "| --- | --- |",
    ]
    for category, score in sorted(result.score_breakdown.items()):
        bar = _score_bar(score)
        lines.append(f"| {category.replace('_', ' ').title()} | {bar} {score:.0f}/100 |")

    return "\n".join(lines)


def _score_bar(score: float) -> str:
    """Return a small visual bar for a 0-100 score."""
    filled = int(score / 10)
    return "\u2588" * filled + "\u2591" * (10 - filled)


def preflight_check(target: str, mode: str, config: DecibenchConfig) -> dict[str, Any]:
    """Check configuration before allowing a run. Returns structured dict."""
    ok = True
    findings = []
    actions = []

    # 1. Target check
    if target in ("retell", "vapi"):
        import os
        if not os.environ.get(f"{target.upper()}_API_KEY") and not getattr(config.auth, f"{target}_api_key", None):
            ok = False
            findings.append(f"Missing {target.title()} API key.")
            actions.append(f"Set {target.upper()}_API_KEY or configure in decibench.toml [auth]")

    # 2. Mode check
    if mode in ("semantic", "semantic-local", "semantic-rag"):
        if not config.has_judge:
            ok = False
            findings.append("Semantic evaluation requires an LLM judge.")
            actions.append("Run `decibench models preset ollama balanced` (local) or configure OpenAI/Anthropic.")

    # 3. RAG check
    if mode == "semantic-rag":
        from decibench.rag import RagStore
        if RagStore().chunk_count() == 0:
            ok = False
            findings.append("Corpus is empty.")
            actions.append("Run `decibench rag ingest <files>` to populate knowledge corpus.")

    return {
        "ok": ok,
        "findings": findings,
        "suggested_actions": actions
    }


def format_run_result_rich(result: SuiteResult, run_id: str) -> dict[str, Any]:
    """Format run result into a rich dictionary for MCP output."""
    headline = "ALL PASSED" if result.passed else f"FAILED ({result.failed} failures)"
    
    actions = []
    if result.failed > 0:
        actions.append("Use `list_calls` to find failed runs, then `get_call` to read traces.")
        actions.append("Use `open_workbench` to view results visually.")
    
    return {
        "ok": True,
        "summary": f"Score: {result.decibench_score:.0f}/100 | {headline} | {result.total_scenarios} total scenarios",
        "score": result.decibench_score,
        "passed": result.passed,
        "failed": result.failed,
        "breakdown": format_score_breakdown(result),
        "headline_finding": headline,
        "suggested_actions": actions,
        "run_id": run_id,
    }
