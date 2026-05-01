"""Shared helpers for Decibench MCP tools."""

from __future__ import annotations

from functools import lru_cache

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
