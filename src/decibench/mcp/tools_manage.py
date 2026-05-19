"""MCP tools for environment management and diagnostics."""

from __future__ import annotations

import importlib.util
import shutil

from decibench.mcp._helpers import get_config
from decibench.mcp.server import mcp


@mcp.tool()
def doctor() -> str:
    """Check the Decibench environment and report any issues.

    Verifies: Python version, config file, store, connectors, TTS/STT
    providers, judge configuration, and Node.js availability.

    Returns:
        Health check report with PASS/WARN/FAIL for each check.
    """
    from decibench import __version__
    from decibench.config import find_config
    from decibench.store import default_store_path

    checks: list[tuple[str, str, str]] = []

    # Version
    import platform
    checks.append(("PASS", "Decibench", f"v{__version__}"))
    checks.append(("PASS", "Python", platform.python_version()))

    # Store
    store_path = default_store_path()
    checks.append(("PASS", "Store", str(store_path)))

    # Config
    config_path = find_config()
    if config_path is None:
        checks.append(("WARN", "Config", "No decibench.toml found. Run: decibench init"))
    else:
        checks.append(("PASS", "Config", str(config_path)))

    # Config details
    config = get_config()
    checks.append(("PASS", "Target", config.target.default))
    checks.append(("PASS", "TTS", config.providers.tts))
    checks.append(("PASS", "STT", config.providers.stt))

    # Judge
    if config.providers.judge == "none":
        checks.append(("PASS", "Judge", "Deterministic-only (no LLM judge)"))
    else:
        has_key = bool(config.providers.judge_api_key)
        status = "PASS" if has_key else "WARN"
        detail = f"{config.providers.judge} / {config.providers.judge_model or 'auto'}"
        if not has_key:
            detail += " (no API key — set via env var or decibench auth set)"
        checks.append((status, "Judge", detail))

    # Node.js (needed for bridge connectors)
    node = shutil.which("node")
    checks.append(("PASS" if node else "WARN", "Node.js", node or "Not found (needed for Retell/Vapi bridge)"))

    # RAG Status
    from decibench.rag import RagStore
    try:
        rag_stats = RagStore().stats()
        rag_docs = rag_stats["documents"]
        if rag_docs > 0:
            checks.append(("PASS", "RAG Corpus", f"{rag_docs} documents ({rag_stats['chunks']} chunks)"))
        else:
            checks.append(("PASS", "RAG Corpus", "Empty (run `decibench rag ingest` to populate)"))
    except Exception as e:
        checks.append(("WARN", "RAG Corpus", f"Error: {e}"))

    # Optional packages
    for pkg, label in [("faster_whisper", "Whisper STT"), ("edge_tts", "Edge TTS"), ("uvicorn", "Workbench")]:
        installed = importlib.util.find_spec(pkg) is not None
        checks.append(("PASS" if installed else "WARN", label, "Installed" if installed else "Not installed"))

    # Format output
    lines = ["## Environment Check", ""]
    for status, label, detail in checks:
        icon = {"PASS": "+", "WARN": "!", "FAIL": "x"}.get(status, "?")
        lines.append(f"[{icon}] **{label}**: {detail}")

    passed = sum(1 for s, _, _ in checks if s == "PASS")
    total = len(checks)
    lines.append("")
    lines.append(f"**{passed}/{total}** checks passed.")

    return "\n".join(lines)


@mcp.tool()
def list_connectors() -> str:
    """List all available voice agent connectors and their URI schemes.

    Shows which connector types are registered and how to target them.

    Returns:
        Table of connector schemes, classes, and example URIs.
    """
    from decibench.connectors.registry import _connector_registry

    if not _connector_registry:
        return "No connectors registered. This shouldn't happen — check your installation."

    examples = {
        "demo": "demo",
        "ws": "ws://localhost:8080/ws",
        "http": "http://localhost:3000/agent",
        "exec": "exec:python my_agent.py",
        "retell": "retell://agent_id",
        "vapi": "vapi://assistant_id",
        "elevenlabs": "elevenlabs://agent_abc123",
        "twilio": "twilio://localhost:3000/media-stream",
    }

    lines = [
        "## Available Connectors",
        "",
        "| Scheme | Connector | Example URI |",
        "| --- | --- | --- |",
    ]
    for scheme in sorted(_connector_registry):
        cls_name = _connector_registry[scheme].__name__
        example = examples.get(scheme, f"{scheme}://...")
        lines.append(f"| `{scheme}://` | {cls_name} | `{example}` |")

    lines.append("")
    lines.append(f"**{len(_connector_registry)}** connectors available.")

    return "\n".join(lines)


@mcp.tool()
def list_suites() -> str:
    """List available test suites and their scenario counts.

    Returns:
        Available suites with descriptions.
    """
    from importlib import resources

    from decibench.scenarios.loader import ScenarioLoader

    lines = ["## Available Test Suites", ""]

    loader = ScenarioLoader()

    # Static descriptions for built-ins
    desc_map = {
        "quick": "Fast health check. Covers core metrics: latency, compliance, basic task completion.",
        "full": "Comprehensive test. All metrics including robustness, interruption handling, edge cases.",
        "standard": "Standard extended suite.",
        "acoustic": "Acoustic edge cases.",
        "adversarial": "Adversarial testing.",
    }

    try:
        suite_pkg = resources.files("decibench.scenarios.suites")
        suites = []
        for item in suite_pkg.iterdir():
            if item.is_dir() and not item.name.startswith("_"):
                suites.append(item.name)

        # Ensure full is always listed
        if "full" not in suites:
            suites.append("full")

        for suite in sorted(suites):
            scenarios = loader.load_suite(suite)
            count = len(scenarios)
            if count == 0:
                continue

            desc = desc_map.get(suite, "Custom / RAG-synthesized suite.")
            lines.append(f"### `{suite}` ({count} scenarios)")
            lines.append(f"{desc}")
            lines.append("")

    except Exception as e:
        lines.append(f"Error loading suites: {e}")

    lines.append("Use with: `run_test(target='...', suite='quick')` or `run_test(target='...', suite='full')`")

    return "\n".join(lines)


@mcp.tool()
def open_workbench(run_id: str = "") -> str:
    """Get the URL to open the visual Workbench dashboard.
    
    Args:
        run_id: Optional ID of a specific run to open.
        
    Returns:
        The URL to the local workbench.
    """
    url = "http://127.0.0.1:8000/#/"
    if run_id:
        url = f"http://127.0.0.1:8000/#/runs/{run_id}"

    return (
        f"The Decibench visual workbench is available at: {url}\n\n"
        "Ensure the server is running with `decibench serve`."
    )


@mcp.tool()
def show_scoring() -> str:
    """Show current scoring weights and metric policies.

    Displays:
    - Category weights (how much each area matters to the final score)
    - Metric policies (blocking/scoring/advisory for each metric)
    - Which policies are user overrides vs defaults

    Returns:
        Current scoring configuration.
    """

    config = get_config()
    w = config.scoring.weights
    policies = config.scoring.resolved_policies
    user_overrides = config.scoring.policies

    lines = ["## Scoring Configuration", ""]

    # Weights
    lines.append("### Category Weights")
    lines.append("| Category | Weight |")
    lines.append("| --- | --- |")
    for name, val in [
        ("task_completion", w.task_completion),
        ("latency", w.latency),
        ("audio_quality", w.audio_quality),
        ("conversation", w.conversation),
        ("robustness", w.robustness),
        ("interruption", w.interruption),
        ("compliance", w.compliance),
    ]:
        lines.append(f"| {name.replace('_', ' ').title()} | {val:.0%} |")

    # Policies by tier
    lines.append("")
    lines.append("### Metric Policies")
    lines.append("*blocking* = fails scenario | *scoring* = affects score only | *advisory* = info only")
    lines.append("")

    for tier in ("blocking", "scoring", "advisory"):
        metrics = sorted(k for k, v in policies.items() if v == tier)
        if not metrics:
            continue
        lines.append(f"**{tier.upper()}**:")
        for m in metrics:
            marker = " *(custom)*" if m in user_overrides else ""
            lines.append(f"  - `{m}`{marker}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def configure_scoring(
    weights: str = "",
    policies: str = "",
    reset: bool = False,
) -> str:
    """Configure scoring weights and metric policies.

    Control what matters for YOUR agent. Set category weights to prioritize
    what's important, and set metric policies to control how failures affect
    your score.

    Args:
        weights: Comma-separated weight assignments.
                 Example: "latency=0.30,compliance=0.05,task_completion=0.30,audio_quality=0.10,conversation=0.10,robustness=0.10,interruption=0.05"
                 All 7 weights must sum to 1.0.
        policies: Comma-separated policy assignments.
                  Example: "ai_disclosure=advisory,pii_violations=blocking,task_completion=blocking"
                  Valid policies: blocking, scoring, advisory.
        reset: If true, reset all weights and policies to defaults.

    Returns:
        Updated scoring configuration.
    """
    from decibench.cli._config_file import upsert_toml_key
    from decibench.config import find_config

    config_path = find_config()
    if config_path is None:
        return "No decibench.toml found. Run `decibench init` first, or pass weights/policies via the config."

    if reset:
        text = config_path.read_text(encoding="utf-8")
        defaults = {
            "task_completion": 0.25, "latency": 0.20, "audio_quality": 0.15,
            "conversation": 0.15, "robustness": 0.10, "interruption": 0.10, "compliance": 0.05,
        }
        for key, val in defaults.items():
            text = upsert_toml_key(text, "scoring.weights", key, val)

        # Remove policies section
        lines = text.splitlines()
        new_lines = []
        skip = False
        for line in lines:
            s = line.strip()
            if s == "[scoring.policies]":
                skip = True
                continue
            if skip and s.startswith("["):
                skip = False
            if skip and ("=" in s or not s):
                continue
            new_lines.append(line)
        config_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return "Scoring reset to defaults.\n\n" + show_scoring()

    changes: list[str] = []

    if weights:
        text = config_path.read_text(encoding="utf-8")
        valid_cats = {"task_completion", "latency", "audio_quality", "conversation", "robustness", "interruption", "compliance"}
        for pair in weights.split(","):
            pair = pair.strip()
            if "=" not in pair:
                return f"Bad weight format: '{pair}'. Expected key=value."
            key, val_str = pair.split("=", 1)
            key = key.strip()
            if key not in valid_cats:
                return f"Unknown category: '{key}'. Valid: {', '.join(sorted(valid_cats))}"
            try:
                val = float(val_str.strip())
            except ValueError:
                return f"Invalid weight: '{val_str}'"
            text = upsert_toml_key(text, "scoring.weights", key, val)
            changes.append(f"weight {key} = {val}")
        config_path.write_text(text, encoding="utf-8")

    if policies:
        text = config_path.read_text(encoding="utf-8")
        valid_policies = {"blocking", "scoring", "advisory"}
        for pair in policies.split(","):
            pair = pair.strip()
            if "=" not in pair:
                return f"Bad policy format: '{pair}'. Expected metric=policy."
            metric, policy = pair.split("=", 1)
            metric = metric.strip()
            policy = policy.strip()
            if policy not in valid_policies:
                return f"Invalid policy: '{policy}'. Valid: blocking, scoring, advisory"
            text = upsert_toml_key(text, "scoring.policies", metric, policy)
            changes.append(f"policy {metric} = {policy}")
        config_path.write_text(text, encoding="utf-8")

    if not changes:
        return "No changes specified. Pass weights, policies, or reset=true.\n\n" + show_scoring()

    # Validate
    try:
        from decibench.config import load_config
        load_config(config_path)
    except Exception as e:
        return f"Warning: config validation error: {e}\nWeights must sum to 1.0."

    result_lines = ["**Updated:**"]
    for c in changes:
        result_lines.append(f"  - {c}")
    result_lines.append("")
    result_lines.append(show_scoring())

    return "\n".join(result_lines)
