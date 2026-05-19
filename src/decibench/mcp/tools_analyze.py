"""MCP tools for analyzing test failures and comparing runs."""

from __future__ import annotations

from decibench.mcp._helpers import get_store
from decibench.mcp.server import mcp


@mcp.tool()
def analyze_failures(run_id: str = "") -> str:
    """Analyze what's failing in a test run and suggest fixes.

    Looks at the most recent run (or a specific run) and identifies:
    - Which metrics are failing across the most scenarios
    - Root causes and fix priorities
    - Specific actionable recommendations

    Args:
        run_id: Optional run ID. If empty, uses the most recent run.

    Returns:
        Prioritized failure analysis with fix recommendations.
    """
    store = get_store()

    if not run_id:
        runs = store.list_runs(limit=1)
        if not runs:
            return "No test runs found. Run a test first."
        run_id = runs[0]["id"]

    result = store.get_suite_result(run_id)
    if result is None:
        return f"Run '{run_id}' not found."

    total = result.total_scenarios

    # Aggregate failures across all scenarios
    failures: dict[str, dict] = {}
    for er in result.results:
        for m in er.metrics.values():
            if not m.passed:
                if m.name not in failures:
                    failures[m.name] = {
                        "count": 0,
                        "scenarios": [],
                        "values": [],
                        "threshold": m.threshold,
                        "unit": m.unit,
                        "reasoning": [],
                    }
                failures[m.name]["count"] += 1
                failures[m.name]["scenarios"].append(er.scenario_id)
                failures[m.name]["values"].append(m.value)
                if m.details and m.details.get("judge_reasoning"):
                    failures[m.name]["reasoning"].append(m.details["judge_reasoning"])

    if not failures:
        return f"No failures in this run! Score: {result.decibench_score:.1f}/100. All {total} scenarios passed."

    # Sort by impact (most scenarios affected)
    sorted_failures = sorted(failures.items(), key=lambda x: x[1]["count"], reverse=True)

    lines = [
        f"## Failure Analysis — {result.decibench_score:.1f}/100",
        f"**{result.passed}/{total}** scenarios passed | **{result.failed}** failed",
        "",
        "### Priority Fixes (sorted by impact)",
        "",
    ]

    for rank, (metric_name, info) in enumerate(sorted_failures, 1):
        pct = (info["count"] / total) * 100
        avg_val = sum(info["values"]) / len(info["values"])
        threshold_str = f" (threshold: {info['threshold']}{info['unit']})" if info["threshold"] is not None else ""

        lines.append(f"**{rank}. {metric_name.replace('_', ' ').title()}** — fails {info['count']}/{total} ({pct:.0f}%)")
        lines.append(f"   Average value: {avg_val:.1f}{info['unit']}{threshold_str}")

        # Add fix recommendations
        fix = _get_fix_recommendation(metric_name, info)
        if fix:
            lines.append(f"   **Fix**: {fix}")

        # Add judge reasoning if available
        if info["reasoning"]:
            first_reasoning = info["reasoning"][0]
            short = first_reasoning[:200] + "..." if len(first_reasoning) > 200 else first_reasoning
            lines.append(f"   **AI Judge says**: {short}")

        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def compare_runs(run_id_a: str, run_id_b: str) -> str:
    """Compare two test runs side by side.

    Shows score changes, metric improvements/regressions, and which
    scenarios changed status (pass→fail or fail→pass).

    Args:
        run_id_a: First run ID (typically the older run).
        run_id_b: Second run ID (typically the newer run).

    Returns:
        Side-by-side comparison with delta analysis.
    """
    store = get_store()
    a = store.get_suite_result(run_id_a)
    b = store.get_suite_result(run_id_b)

    if a is None:
        return f"Run A '{run_id_a}' not found."
    if b is None:
        return f"Run B '{run_id_b}' not found."

    delta = b.decibench_score - a.decibench_score
    direction = "improved" if delta > 0 else "regressed" if delta < 0 else "unchanged"
    arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"

    lines = [
        "## Run Comparison",
        "",
        "| | Run A | Run B | Delta |",
        "| --- | --- | --- | --- |",
        f"| **Score** | {a.decibench_score:.1f} | {b.decibench_score:.1f} | {arrow} {abs(delta):.1f} ({direction}) |",
        f"| **Passed** | {a.passed}/{a.total_scenarios} | {b.passed}/{b.total_scenarios} | {b.passed - a.passed:+d} |",
        f"| **Suite** | {a.suite} | {b.suite} | |",
        f"| **Mode** | {a.evaluation_mode} | {b.evaluation_mode} | |",
    ]

    # Category breakdown comparison
    if a.score_breakdown and b.score_breakdown:
        lines.append("")
        lines.append("### Category Changes")
        lines.append("| Category | Before | After | Delta |")
        lines.append("| --- | --- | --- | --- |")
        for cat_name, score_a in a.score_breakdown.items():
            score_b = b.score_breakdown.get(cat_name)
            if score_b is not None:
                d = score_b - score_a
                arr = "↑" if d > 0 else "↓" if d < 0 else "→"
                lines.append(f"| {cat_name.replace('_', ' ').title()} | {score_a:.0f} | {score_b:.0f} | {arr} {abs(d):.0f} |")

    # Scenario status changes
    a_scenarios = {r.scenario_id: r.passed for r in a.results}
    b_scenarios = {r.scenario_id: r.passed for r in b.results}

    newly_passing = [s for s in b_scenarios if b_scenarios[s] and not a_scenarios.get(s, False)]
    newly_failing = [s for s in b_scenarios if not b_scenarios[s] and a_scenarios.get(s, True)]

    if newly_passing:
        lines.append("")
        lines.append(f"### Newly Passing ({len(newly_passing)})")
        for s in newly_passing:
            lines.append(f"  - {s}")

    if newly_failing:
        lines.append("")
        lines.append(f"### Newly Failing ({len(newly_failing)})")
        for s in newly_failing:
            lines.append(f"  - {s}")

    return "\n".join(lines)


def _get_fix_recommendation(metric: str, info: dict) -> str:
    """Return an actionable fix recommendation for a failing metric."""
    recs = {
        "ai_disclosure": "Add 'I am an AI assistant' to the agent's greeting prompt. Required for compliance.",
        "compliance_score": "Check AI disclosure, PII handling, and PCI rules in the agent config.",
        "pii_violations": "Agent is leaking PII. Add data masking to sensitive fields (SSN, credit card, etc).",
        "task_completion": "Agent isn't achieving caller goals. Wire up tool calls and ensure follow-through on requests.",
        "hallucination_rate": "Agent is making ungrounded claims. Add retrieval/grounding to prevent fabrication.",
        "ttfw_ms": "Slow first response. Optimize cold start or add a filler phrase while processing.",
        "wer": "High word error rate. Check audio quality, STT model, or agent pronunciation.",
        "tool_call_correctness": "Expected tool calls aren't being invoked. Check function definitions in agent config.",
        "slot_extraction_accuracy": "Agent isn't extracting key data. Improve slot-filling prompts.",
        "silence_pct": "Too much dead air. Reduce processing time or add conversation fillers.",
    }

    # Check keyword-based metrics
    if metric.startswith("keyword_presence"):
        missing = set()
        for s in info["scenarios"]:
            pass  # Could extract missing keywords from details
        return "Agent missing expected phrases. Update prompt to include required keywords."

    return recs.get(metric, "")
