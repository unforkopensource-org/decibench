"""decibench run — the primary command. Run test scenarios against a voice agent."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

from decibench.config import load_config
from decibench.llm_catalog import (
    estimate_run_cost,
    get_provider_catalog,
    supported_providers,
)
from decibench.orchestrator import Orchestrator
from decibench.reporters.ci_reporter import CIReporter
from decibench.reporters.json_reporter import JSONReporter
from decibench.reporters.markdown_reporter import MarkdownReporter
from decibench.reporters.rich_reporter import RichReporter
from decibench.secrets import load_secret, store_secret
from decibench.store import RunStore, default_store_path

if TYPE_CHECKING:
    from decibench.config import DecibenchConfig


@click.command("run")
@click.option(
    "--target", "-t",
    default=None,
    help="Target agent URI (ws://, exec:, http://, demo). Default: from config.",
)
@click.option(
    "--suite", "-s",
    default="quick",
    help="Test suite to run (quick, standard, full).",
)
@click.option(
    "--scenario",
    default=None,
    help="Run a single scenario by ID (e.g., quick-greeting-001).",
)
@click.option(
    "--config", "-c",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to decibench.toml.",
)
@click.option(
    "--profile", "-p",
    default=None,
    help="Config profile to use (dev, ci, benchmark).",
)
@click.option(
    "--noise",
    default=None,
    help="Comma-separated noise levels (clean,cafe,street).",
)
@click.option(
    "--accents",
    default=None,
    help="Comma-separated accent codes (en-US,en-IN,en-GB).",
)
@click.option(
    "--parallel",
    default=5,
    type=int,
    help="Max concurrent scenario runs.",
)
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory for results.",
)
@click.option(
    "--store",
    "store_path",
    type=click.Path(path_type=Path),
    default=None,
    help="SQLite store path. Defaults to .decibench/decibench.sqlite.",
)
@click.option(
    "--no-store",
    is_flag=True,
    default=False,
    help="Do not persist this run in the local Decibench store.",
)
@click.option(
    "--min-score",
    type=float,
    default=None,
    help="Minimum score threshold (overrides config).",
)
@click.option(
    "--exit-code-on-fail",
    is_flag=True,
    default=False,
    help="Exit with code 1 if score < min-score.",
)
@click.option(
    "--fail-under",
    type=float,
    default=None,
    help="Exit with code 1 if score is less than this value.",
)
@click.option(
    "--fail-on",
    default=None,
    help="Comma-separated categories to fail on (e.g. compliance,latency).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["rich", "json", "markdown", "ci", "junit"]),
    default="rich",
    help="Output format.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Enable verbose logging.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate config and list scenarios without executing them.",
)
@click.option(
    "--mode",
    "eval_mode",
    type=click.Choice(["deterministic", "semantic", "semantic-local", "ask"]),
    default="ask",
    help="Evaluation mode: deterministic (free), semantic (cloud LLM), semantic-local (free Ollama), or ask (interactive).",
)
def run_cmd(
    target: str | None,
    suite: str,
    scenario: str | None,
    config_path: Path | None,
    profile: str | None,
    noise: str | None,
    accents: str | None,
    parallel: int,
    output: Path | None,
    store_path: Path | None,
    no_store: bool,
    min_score: float | None,
    exit_code_on_fail: bool,
    fail_under: float | None,
    fail_on: str | None,
    output_format: str,
    verbose: bool,
    dry_run: bool,
    eval_mode: str,
) -> None:
    """Run test scenarios against a voice agent."""
    import logging

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load config
    config = load_config(config_path, profile)

    # ── Interactive mode selection ──
    if not dry_run:
        config = _resolve_eval_mode(config, eval_mode, suite)

    # Resolve target
    resolved_target = target or config.target.default

    # Parse comma-separated options
    noise_levels = noise.split(",") if noise else None
    accent_list = accents.split(",") if accents else None
    fail_categories = fail_on.split(",") if fail_on else []

    # --- Dry run: validate config and list scenarios ---
    if dry_run:
        _dry_run(config, resolved_target, suite, scenario, noise_levels, accent_list)
        return

    # Resolve min score (fail_under overrides min_score property)
    effective_min_score = (
        fail_under
        if fail_under is not None
        else (min_score if min_score is not None else config.ci.min_score)
    )
    # Enable failure gate if either old flag or new flag is used
    fail_gate_active = exit_code_on_fail or (fail_under is not None) or fail_categories

    # Create output directory
    if output:
        output.mkdir(parents=True, exist_ok=True)

    # Set up progress bar for rich format
    progress = None
    task_id = None

    if output_format == "rich" and not scenario:
        try:
            from rich.progress import (
                BarColumn,
                Progress,
                SpinnerColumn,
                TextColumn,
                TimeElapsedColumn,
            )
            progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed}/{task.total})"),
                TimeElapsedColumn(),
                transient=True,
            )
        except ImportError:
            pass

    def on_progress(scenario_id: str, passed: bool, score: float, current: int, total: int) -> None:
        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        if progress and task_id is not None:
            progress.update(task_id, completed=current, description=f"  {scenario_id} {status}")

    # Force serial execution for local Ollama to avoid timeouts/overload
    from decibench.llm_catalog import judge_provider_from_uri
    if judge_provider_from_uri(config.providers.judge) == "ollama" and parallel == 5:
        parallel = 1

    # Run
    orchestrator = Orchestrator(config)

    if progress:
        progress.start()
        # We don't know total yet, will be set by orchestrator
        task_id = progress.add_task("Starting...", total=100)

    try:
        result = asyncio.run(orchestrator.run_suite(
            target=resolved_target,
            suite=suite,
            noise_levels=noise_levels,
            accents=accent_list,
            parallel=parallel,
            scenario_filter=scenario,
            on_progress=on_progress if progress else None,
        ))
    finally:
        if progress:
            progress.stop()

    if not no_store:
        store = RunStore(store_path or default_store_path())
        run_id = store.save_suite_result(result)
        if verbose:
            click.echo(f"Stored run: {run_id} ({store.path})")

    # Update progress total after we know it
    if progress and task_id is not None:
        progress.update(task_id, total=result.total_scenarios, completed=result.total_scenarios)

    # Output results
    if output_format == "json" or output:
        json_path = (output / "results.json") if output else None
        json_str = JSONReporter.report(result, json_path)
        if output_format == "json" and not output:
            click.echo(json_str)

    if output_format == "rich":
        RichReporter().report_suite(result)

    if output_format == "markdown":
        md_path = (output / "report.md") if output else None
        md = MarkdownReporter.report(result, md_path)
        if not output:
            click.echo(md)

    if output_format == "ci":
        CIReporter.report(result, effective_min_score)

    if output_format == "junit":
        from decibench.reporters.junit import format_junit_xml
        junit_xml = format_junit_xml(result)
        if not output:
            click.echo(junit_xml)
        else:
            (output / "junit.xml").write_text(junit_xml, encoding="utf-8")

    # Automatic failure: exit nonzero when every single scenario failed due
    # to execution or configuration errors — regardless of --fail-under flags.
    # This catches "RETELL_API_KEY missing" and similar total-failure cases
    # that would otherwise silently return 0.
    all_execution_failures = (
        result.total_scenarios > 0
        and result.failed == result.total_scenarios
        and all(
            any("Execution error" in f or "error" in f.lower() for f in er.failures)
            for er in result.results
            if er.failures
        )
    )
    if all_execution_failures:
        click.echo(
            f"All {result.total_scenarios} scenario(s) failed with execution errors. "
            "Check your target, credentials, and configuration.",
            err=True,
        )
        sys.exit(1)

    # Evaluate Threshold Failures
    if fail_gate_active:
        failed = False

        # Check overall score
        if result.decibench_score < effective_min_score:
            click.echo(
                f"  [Error] Score {result.decibench_score:.1f} "
                f"is lower than --fail-under {effective_min_score}",
                err=True,
            )
            failed = True

        # Check specific failure categories
        if fail_categories:
            for er in result.results:
                matched_fails = [c for c in er.failure_summary if c in fail_categories]
                if matched_fails:
                    click.echo(
                        f"  [Error] Scenario {er.scenario_id} triggered "
                        f"--fail-on for categories: {matched_fails}",
                        err=True,
                    )
                    failed = True

        if failed:
            sys.exit(1)

    # Write JSON + markdown output even for non-JSON formats if output dir specified
    if output and output_format != "json":
        JSONReporter.report(result, output / "results.json")
        MarkdownReporter.report(result, output / "report.md")

    # Generate HTML dashboard report
    if output:
        from decibench.reporters.html_reporter import HTMLReporter
        HTMLReporter.report(result, output / "dashboard.html")
        click.echo(f"\nDashboard: {output / 'dashboard.html'}")


def _resolve_eval_mode(
    config: DecibenchConfig,
    eval_mode: str,
    suite: str,
) -> DecibenchConfig:
    """Resolve evaluation mode, prompting interactively when needed."""
    from decibench.scenarios.loader import ScenarioLoader

    # If config already has a judge and user didn't explicitly ask for deterministic
    if config.has_judge and eval_mode != "deterministic":
        return config

    # If explicit deterministic, ensure judge is disabled
    if eval_mode == "deterministic":
        config.providers.judge = "none"
        config.providers.judge_model = ""
        return config

    # If explicit semantic, try to auto-detect provider from env vars
    if eval_mode == "semantic":
        if config.has_judge:
            return config
        # Auto-detect: check which provider keys are available in env
        for auto_prov in ["gemini", "openai", "anthropic"]:
            key = load_secret(auto_prov)
            if key:
                catalog = get_provider_catalog(auto_prov)
                config.providers.judge = catalog.judge_uri
                config.providers.judge_model = catalog.budget_model
                config.providers.judge_api_key = key
                click.echo(
                    f"  Auto-detected {click.style(catalog.display_name, bold=True)} key "
                    f"-> using {catalog.budget_model} judge"
                )
                return config
        # Check if Ollama is running as fallback
        if _try_setup_ollama(config):
            return config
        # No key found — fall through to interactive provider selection

    # If explicit semantic-local, set up Ollama directly
    if eval_mode == "semantic-local":
        if _try_setup_ollama(config, interactive=True):
            return config
        click.echo(click.style("  Ollama not available. Install from: https://ollama.com", fg="red"))
        raise SystemExit(1)

    # ── Interactive mode selection ──
    if eval_mode == "ask" and not config.has_judge:
        # Count scenarios for cost estimate
        try:
            num_scenarios = len(ScenarioLoader().load_suite(suite))
        except Exception:
            num_scenarios = 10

        # Check Ollama availability for option display
        from decibench.providers.judge.ollama import is_ollama_running

        ollama_available = is_ollama_running()

        click.echo()
        click.echo(click.style("  Evaluation Mode", bold=True))
        click.echo()
        click.echo("  [1]  Deterministic only      " + click.style("FREE", fg="green", bold=True) + "  No API key needed")
        click.echo("       Latency, Audio Quality, Compliance, Keywords, Silence")
        click.echo(click.style("       Cannot detect hallucinations or assess task success", fg="yellow"))
        click.echo()

        if ollama_available:
            click.echo("  [2]  Semantic (Local Model)   " + click.style("FREE", fg="green", bold=True) + "  Ollama detected!")
        else:
            click.echo("  [2]  Semantic (Local Model)   " + click.style("FREE", fg="green", bold=True) + "  Requires Ollama")
        click.echo("       Everything in [1] PLUS:")
        click.echo(click.style("       + Hallucination detection  + Task completion  + Coherence", fg="green"))
        click.echo("       Runs locally on your machine — no API key, no cost")
        click.echo()

        click.echo("  [3]  Semantic (Cloud)         " + click.style(f"~${_estimate_suite_cost('gemini', num_scenarios)}", fg="cyan", bold=True))
        click.echo("       Same as [2] but uses a cloud LLM (faster, needs API key)")
        click.echo()

        choice = click.prompt("  Select mode", type=click.Choice(["1", "2", "3"]), default="1")

        if choice == "1":
            config.providers.judge = "none"
            config.providers.judge_model = ""
            return config

        if choice == "2":
            # Local Ollama path
            if _try_setup_ollama(config, interactive=True):
                return config
            # Ollama not available — guide user
            click.echo()
            click.echo(click.style("  Ollama is not running.", fg="red"))
            click.echo()
            click.echo("  Quick setup:")
            click.echo("    1. Install Ollama:  " + click.style("https://ollama.com", fg="cyan"))
            click.echo("    2. Start server:    " + click.style("ollama serve", bold=True))
            click.echo("    3. Run decibench again")
            click.echo()
            click.echo("  Or press Enter to continue with a cloud provider instead.")
            click.echo()
            fallback = click.confirm("  Continue with cloud provider?", default=True)
            if not fallback:
                raise SystemExit(0)
            # Fall through to cloud provider selection

        # choice == "3" or fallback from choice "2": cloud provider selection

    # ── Cloud provider selection ──
    providers = list(supported_providers())
    # Order: cheapest first, exclude ollama (it's the local option)
    provider_order = ["gemini", "openai", "anthropic"]
    providers = [p for p in provider_order if p in providers]

    click.echo()
    click.echo(click.style("  Cloud LLM Provider", bold=True))
    click.echo()

    try:
        num_scenarios = len(ScenarioLoader().load_suite(suite))
    except Exception:
        num_scenarios = 10

    provider_details = {
        "gemini": ("Google Gemini", "gemini-2.5-flash-lite", "Cheapest"),
        "openai": ("OpenAI", "gpt-4.1-nano", "Fast"),
        "anthropic": ("Anthropic", "claude-haiku-4-5", "Most accurate"),
    }

    for i, p in enumerate(providers, 1):
        name, model, tag = provider_details.get(p, (p, "unknown", ""))
        cost = _estimate_suite_cost(p, num_scenarios)
        click.echo(f"  [{i}]  {name:<20} {click.style(model, fg='cyan')}")
        click.echo(f"       {tag} · ~${cost} for {num_scenarios} scenarios")
        click.echo()

    idx = click.prompt(
        "  Provider",
        type=click.Choice([str(i) for i in range(1, len(providers) + 1)]),
        default="1",
    )
    chosen_provider = providers[int(idx) - 1]
    catalog = get_provider_catalog(chosen_provider)

    # ── API key ──
    existing_key = load_secret(chosen_provider)
    if existing_key:
        masked = existing_key[:8] + "..." + existing_key[-4:]
        click.echo(f"  Using saved key: {masked}")
        api_key = existing_key
    else:
        click.echo()
        api_key = click.prompt(
            f"  Paste your {catalog.display_name} API key",
            hide_input=True,
        )
        if api_key:
            try:
                store_secret(chosen_provider, api_key)
                click.echo(click.style("  Key saved to local keyring", fg="green"))
            except RuntimeError:
                click.echo("  Key will be used for this run only (keyring not available)")

    # Apply to config
    config.providers.judge = catalog.judge_uri
    config.providers.judge_model = catalog.budget_model
    config.providers.judge_api_key = api_key
    click.echo()
    click.echo(
        f"  Running with {click.style(catalog.display_name, bold=True)} "
        f"({catalog.budget_model}) judge"
    )
    click.echo()
    return config


def _try_setup_ollama(
    config: DecibenchConfig,
    interactive: bool = False,
) -> bool:
    """Try to configure Ollama as the judge. Returns True on success.

    When interactive=True, shows model selection and pulls if needed.
    When interactive=False (auto-detect), only succeeds if model is already pulled.
    """
    from decibench.providers.judge.ollama import (
        DEFAULT_MODEL,
        RECOMMENDED_MODELS,
        ensure_model,
        is_model_available,
        is_ollama_running,
        setup_ollama_judge,
    )

    if not is_ollama_running():
        return False

    if interactive:
        # Show model selection
        click.echo()
        click.echo(click.style("  Local Model Selection", bold=True))
        click.echo()

        for i, (name, size, desc) in enumerate(RECOMMENDED_MODELS, 1):
            available = is_model_available(name)
            status = click.style(" (ready)", fg="green") if available else ""
            default_tag = click.style(" [recommended]", fg="cyan") if i == 1 else ""
            click.echo(f"  [{i}]  {name:<18} {size:<10} {desc}{default_tag}{status}")

        click.echo()
        idx = click.prompt(
            "  Select model",
            type=click.Choice([str(i) for i in range(1, len(RECOMMENDED_MODELS) + 1)]),
            default="1",
        )
        chosen_model = RECOMMENDED_MODELS[int(idx) - 1][0]

        # Pull if needed (lazy download)
        if not ensure_model(chosen_model, show_progress=True):
            return False

        judge_uri, judge_model, api_key = setup_ollama_judge(chosen_model)
    else:
        # Auto-detect: only use if default model is already available
        if not is_model_available(DEFAULT_MODEL):
            return False
        judge_uri, judge_model, api_key = setup_ollama_judge()

    config.providers.judge = judge_uri
    config.providers.judge_model = judge_model
    config.providers.judge_api_key = api_key

    click.echo(
        f"  Using {click.style('Ollama', bold=True)} local model: "
        f"{click.style(judge_model, fg='cyan')} " + click.style("(FREE)", fg="green")
    )
    click.echo()
    return True


def _estimate_suite_cost(provider: str, num_scenarios: int) -> str:
    """Format estimated cost as a human-readable string."""
    cost = estimate_run_cost(provider, num_scenarios)
    if cost < 0.01:
        return f"{cost:.4f}"
    return f"{cost:.3f}"


def _dry_run(
    config: DecibenchConfig,
    target: str,
    suite: str,
    scenario_filter: str | None,
    noise_levels: list[str] | None,
    accents: list[str] | None,
) -> None:
    """Validate config, test target connectivity, list scenarios."""
    import importlib.util

    from decibench.scenarios.loader import ScenarioLoader

    click.echo("DRY RUN -- validating configuration\n")

    # 1. Config summary
    click.echo(f"  Target:     {target}")
    click.echo(f"  Suite:      {suite}")
    click.echo(f"  TTS:        {config.providers.tts}")
    click.echo(f"  STT:        {config.providers.stt}")
    click.echo(f"  WS protocol: {config.connector.ws_protocol}")
    click.echo()

    # 2. Dependency check
    issues: list[str] = []
    if not importlib.util.find_spec("edge_tts"):
        issues.append("edge-tts not installed (pip install edge-tts)")
    if not importlib.util.find_spec("faster_whisper"):
        issues.append("faster-whisper not installed (pip install decibench[stt-whisper])")

    if issues:
        click.echo("  Dependency issues:")
        for issue in issues:
            click.echo(f"    WARN  {issue}")
        click.echo()

    # 3. Target connectivity
    if target not in ("demo", "demo://"):
        click.echo("  Testing target connectivity...")
        import asyncio

        async def _probe() -> tuple[bool, str]:
            if target.startswith(("ws://", "wss://")):
                import websockets
                try:
                    ws = await asyncio.wait_for(
                        websockets.connect(target, close_timeout=3), timeout=5.0
                    )
                    await ws.close()
                    return True, f"Connected to {target}"
                except Exception as exc:
                    return False, f"Failed: {exc}"
            if target.startswith(("http://", "https://")):
                import httpx
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        resp = await client.head(target)
                        return True, f"HTTP {resp.status_code}"
                except Exception as exc:
                    return False, f"Failed: {exc}"
            return True, f"Cannot probe {target} (skipped)"

        ok, msg = asyncio.run(_probe())
        status = "PASS" if ok else "FAIL"
        click.echo(f"    {status}  {msg}")
        click.echo()

    # 4. Load and list scenarios
    loader = ScenarioLoader()
    scenarios = loader.load_suite(suite)
    if scenario_filter:
        scenarios = [s for s in scenarios if scenario_filter in s.id]
    if noise_levels or accents:
        scenarios = loader.expand_variants(scenarios, noise_levels, accents)

    click.echo(f"  Scenarios to run: {len(scenarios)}")
    for s in scenarios[:20]:
        click.echo(f"    - {s.id}: {s.description}")
    if len(scenarios) > 20:
        click.echo(f"    ... and {len(scenarios) - 20} more")

    click.echo("\nDry run complete. Remove --dry-run to execute.")
