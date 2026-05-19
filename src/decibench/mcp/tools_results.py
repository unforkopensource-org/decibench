"""MCP tools for viewing test results and run history."""

from __future__ import annotations

from decibench.mcp._helpers import format_score_breakdown, get_store
from decibench.mcp.server import mcp


@mcp.tool()
def list_runs(limit: int = 10) -> str:
    """List recent Decibench test runs with scores.

    Shows run history sorted by most recent first. Use this to find
    run IDs for deeper analysis with get_run_detail.

    Args:
        limit: Maximum number of runs to return (default: 10).

    Returns:
        Table of recent runs with scores, pass rates, and evaluation modes.
    """
    store = get_store()
    runs = store.list_runs(limit=limit)

    if not runs:
        return "No test runs found. Run a test first with the `run_test` tool."

    lines = [
        "| Run ID | Score | Passed | Suite | Mode | Target | Time |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in runs:
        run_id = r["id"][:30] + "..." if len(r["id"]) > 30 else r["id"]
        score = r.get("score", 0)
        passed = r.get("passed", 0)
        total = r.get("total_scenarios", 0)
        suite = r.get("suite", "?")
        mode = r.get("evaluation_mode", "deterministic")
        target = r.get("target", "?")
        if len(target) > 25:
            target = target[:22] + "..."
        ts = r.get("timestamp", "")[:16]
        lines.append(
            f"| `{run_id}` | **{score:.1f}** | {passed}/{total} | {suite} | {mode} | {target} | {ts} |"
        )

    return "\n".join(lines)


@mcp.tool()
def get_run_detail(run_id: str) -> str:
    """Get detailed results for a specific test run.

    Shows the full score breakdown, every scenario result, per-metric
    details, and AI judge reasoning (if semantic mode was used).

    Args:
        run_id: The run ID from list_runs. Partial matches work —
                if only one run matches the prefix, it will be used.

    Returns:
        Complete run analysis with score breakdown, failures, and per-scenario details.
    """
    store = get_store()

    # Try exact match first, then prefix match
    result = store.get_suite_result(run_id)
    if result is None:
        # Try prefix match
        runs = store.list_runs(limit=50)
        matches = [r for r in runs if r["id"].startswith(run_id)]
        if len(matches) == 1:
            result = store.get_suite_result(matches[0]["id"])
        elif len(matches) > 1:
            ids = "\n".join(f"  - `{r['id']}`" for r in matches[:5])
            return f"Multiple runs match '{run_id}':\n{ids}\nBe more specific."

    if result is None:
        return f"Run '{run_id}' not found. Use `list_runs` to see available runs."

    lines = [
        f"## Run: {result.suite} → {result.target}",
        f"**Score**: {result.decibench_score:.1f}/100",
        f"**Mode**: {result.evaluation_mode}",
    ]

    if result.judge_model and result.judge_model != "none":
        lines.append(f"**Judge**: {result.judge_model}")

    lines.append("")
    lines.append("### Score Breakdown")
    lines.append(format_score_breakdown(result))

    # Per-scenario results
    lines.append("")
    lines.append("### Scenario Results")

    for er in result.results:
        status = "PASS" if er.passed else "FAIL"
        lines.append(f"\n#### {er.scenario_id} — {status} ({er.score:.0f}/100)")

        for m in er.metrics.values():
            icon = "✓" if m.passed else "✗"
            detail = ""
            if m.details:
                reasoning = m.details.get("judge_reasoning", "")
                if reasoning:
                    # Show first 150 chars of judge reasoning
                    short = reasoning[:150] + "..." if len(reasoning) > 150 else reasoning
                    detail = f" — *{short}*"
            lines.append(f"  - {icon} **{m.name}**: {m.value}{m.unit}{detail}")

    return "\n".join(lines)


@mcp.tool()
def get_latest_score() -> str:
    """Get the score from the most recent test run.

    Quick way to check: "What's my current Decibench score?"

    Returns:
        Score summary with breakdown.
    """
    store = get_store()
    runs = store.list_runs(limit=1)

    if not runs:
        return "No test runs found. Run a test first with the `run_test` tool."

    result = store.get_suite_result(runs[0]["id"])
    if result is None:
        return "Could not load the latest run."

    lines = [
        f"**Latest Decibench Score: {result.decibench_score:.1f}/100**",
        f"Suite: {result.suite} | Target: {result.target} | Mode: {result.evaluation_mode}",
        f"Passed: {result.passed}/{result.total_scenarios}",
        "",
        format_score_breakdown(result),
    ]

    return "\n".join(lines)
