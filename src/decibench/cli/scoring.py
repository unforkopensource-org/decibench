"""decibench scoring -- view and configure metric weights and policies."""

from __future__ import annotations

from pathlib import Path

import click

from decibench.config import (
    DecibenchConfig,
    MetricPolicy,
    find_config,
    load_config,
)


@click.group("scoring")
def scoring_cmd() -> None:
    """View and configure scoring weights and metric policies."""


@scoring_cmd.command("show")
def scoring_show() -> None:
    """Show current scoring weights and metric policies."""
    config = _load()

    click.echo("## Category Weights")
    w = config.scoring.weights
    for name, val in [
        ("task_completion", w.task_completion),
        ("latency", w.latency),
        ("audio_quality", w.audio_quality),
        ("conversation", w.conversation),
        ("robustness", w.robustness),
        ("interruption", w.interruption),
        ("compliance", w.compliance),
    ]:
        bar = "\u2588" * int(val * 40)
        click.echo(f"  {name:<20} {val:.2f}  {bar}")

    click.echo()
    click.echo("## Metric Policies")
    click.echo("  (blocking = fails scenario | scoring = affects score | advisory = info only)")
    click.echo()

    policies = config.scoring.resolved_policies
    user_overrides = config.scoring.policies

    for policy_tier in ("blocking", "scoring", "advisory"):
        metrics = sorted(k for k, v in policies.items() if v == policy_tier)
        if not metrics:
            continue
        click.echo(f"  [{policy_tier.upper()}]")
        for m in metrics:
            marker = " *" if m in user_overrides else ""
            click.echo(f"    {m}{marker}")
        click.echo()

    if user_overrides:
        click.echo("  * = user override (in decibench.toml)")


@scoring_cmd.command("set-weight")
@click.argument("assignments", nargs=-1, required=True)
def scoring_set_weight(assignments: tuple[str, ...]) -> None:
    """Set category weights. Example: decibench scoring set-weight latency=0.30 compliance=0.05

    Weights must sum to 1.0 across all 7 categories.
    """
    config_path = _require_config()
    config = load_config(config_path)

    # Parse assignments
    updates: dict[str, float] = {}
    for assignment in assignments:
        if "=" not in assignment:
            raise click.BadParameter(f"Expected key=value, got: {assignment}")
        key, val_str = assignment.split("=", 1)
        key = key.strip()
        try:
            val = float(val_str.strip())
        except ValueError:
            raise click.BadParameter(f"Invalid weight value: {val_str}")  # noqa: B904
        valid_cats = {"task_completion", "latency", "audio_quality", "conversation", "robustness", "interruption", "compliance"}
        if key not in valid_cats:
            raise click.BadParameter(f"Unknown category: {key}. Valid: {', '.join(sorted(valid_cats))}")
        updates[key] = val

    # Apply and validate
    from decibench.cli._config_file import upsert_toml_key

    text = config_path.read_text(encoding="utf-8")
    for key, val in updates.items():
        text = upsert_toml_key(text, "scoring.weights", key, val)
    config_path.write_text(text, encoding="utf-8")

    # Validate the result
    try:
        load_config(config_path)
    except Exception as e:
        click.echo(f"Warning: {e}")
        click.echo("Weights must sum to 1.0. Adjust other categories to compensate.")
        return

    click.echo("Weights updated:")
    for key, val in updates.items():
        click.echo(f"  {key} = {val}")


@scoring_cmd.command("set-policy")
@click.argument("assignments", nargs=-1, required=True)
def scoring_set_policy(assignments: tuple[str, ...]) -> None:
    """Set metric policies. Example: decibench scoring set-policy ai_disclosure=advisory pii_violations=blocking

    Policies: blocking, scoring, advisory
    """
    config_path = _require_config()

    updates: dict[str, MetricPolicy] = {}
    valid_policies = {"blocking", "scoring", "advisory"}

    for assignment in assignments:
        if "=" not in assignment:
            raise click.BadParameter(f"Expected metric=policy, got: {assignment}")
        metric, policy = assignment.split("=", 1)
        metric = metric.strip()
        policy = policy.strip()
        if policy not in valid_policies:
            raise click.BadParameter(f"Invalid policy: {policy}. Valid: {', '.join(sorted(valid_policies))}")
        updates[metric] = policy  # type: ignore[assignment]

    from decibench.cli._config_file import upsert_toml_key

    text = config_path.read_text(encoding="utf-8")
    for metric, policy in updates.items():
        text = upsert_toml_key(text, "scoring.policies", metric, policy)
    config_path.write_text(text, encoding="utf-8")

    click.echo("Policies updated:")
    for metric, policy in updates.items():
        click.echo(f"  {metric} = {policy}")


@scoring_cmd.command("reset")
def scoring_reset() -> None:
    """Reset scoring weights and policies to defaults."""
    config_path = _require_config()

    from decibench.cli._config_file import upsert_toml_key

    text = config_path.read_text(encoding="utf-8")

    # Reset weights to defaults
    defaults = {
        "task_completion": 0.25,
        "latency": 0.20,
        "audio_quality": 0.15,
        "conversation": 0.15,
        "robustness": 0.10,
        "interruption": 0.10,
        "compliance": 0.05,
    }
    for key, val in defaults.items():
        text = upsert_toml_key(text, "scoring.weights", key, val)

    # Remove policies section by clearing known keys
    # (upsert with empty string effectively resets)
    config_path.write_text(text, encoding="utf-8")

    # Remove [scoring.policies] entries by rewriting without them
    lines = text.splitlines()
    new_lines = []
    skip_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "[scoring.policies]":
            skip_section = True
            continue
        if skip_section and stripped.startswith("["):
            skip_section = False
        if skip_section and ("=" in stripped or not stripped):
            continue
        new_lines.append(line)
    config_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    click.echo("Scoring reset to defaults.")


def _load() -> DecibenchConfig:
    config_path = find_config()
    return load_config(config_path)


def _require_config() -> Path:
    config_path = find_config()
    if config_path is None:
        raise click.ClickException("No decibench.toml found. Run: decibench init")
    return config_path
