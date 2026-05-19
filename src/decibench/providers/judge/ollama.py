"""Ollama integration — free local semantic evaluation.

Provides auto-detection of a running Ollama instance, lazy model
pulling with progress display, and configuration helpers. The actual
inference uses the OpenAI-compatible judge (openai_compat.py) since
Ollama exposes a fully compatible /v1/chat/completions endpoint.

Recommended model: llama3.2:3b (~2.0 GB, runs on 8 GB RAM).
"""

from __future__ import annotations

import logging
import sys
import time

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_OPENAI_URL = f"{OLLAMA_BASE_URL}/v1"

# Models ranked by quality-to-size ratio for semantic evaluation.
# All fit in 8 GB RAM. First entry is the default.
RECOMMENDED_MODELS: list[tuple[str, str, str]] = [
    ("llama3.2:3b", "~2.0 GB", "Meta's compact model, good general quality"),
    ("qwen2.5:7b", "~4.7 GB", "Best quality/size ratio for evaluation"),
    ("qwen2.5:3b", "~2.0 GB", "Faster, lower RAM, slightly less accurate"),
    ("phi3:mini", "~2.3 GB", "Microsoft's small model, fast inference"),
    ("gemma2:2b", "~1.6 GB", "Google's lightweight model, lowest RAM usage"),
]

DEFAULT_MODEL = RECOMMENDED_MODELS[0][0]


def is_ollama_installed() -> bool:
    """Check if Ollama CLI is installed (available on PATH)."""
    import shutil

    return shutil.which("ollama") is not None


def is_ollama_running(timeout: float = 3.0) -> bool:
    """Check if the Ollama server is running and responding."""
    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def get_local_models(timeout: float = 5.0) -> list[str]:
    """Return list of model names already pulled locally."""
    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def is_model_available(model: str) -> bool:
    """Check if a specific model is already pulled."""
    local = get_local_models()
    # Match both "qwen2.5:7b" and "qwen2.5:7b-instruct-..." variants
    for m in local:
        if m == model or m.startswith(model.split(":")[0]):
            if ":" in model:
                tag = model.split(":", 1)[1]
                if tag in m:
                    return True
            else:
                return True
    return model in local


def pull_model(model: str, show_progress: bool = True) -> bool:
    """Pull (download) an Ollama model with optional progress display.

    This is a blocking call that streams progress. Only call this when
    the user has explicitly chosen to use a local model.

    Returns True on success, False on failure.
    """
    import click

    if show_progress:
        click.echo()
        click.echo(f"  Downloading {click.style(model, bold=True)} ...")
        click.echo("  This is a one-time download. Future runs will be instant.")
        click.echo()

    try:
        with httpx.stream(
            "POST",
            f"{OLLAMA_BASE_URL}/api/pull",
            json={"name": model, "stream": True},
            timeout=None,
        ) as response:
            response.raise_for_status()
            last_status = ""
            last_update = 0.0

            for line in response.iter_lines():
                if not line:
                    continue
                import json

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                status = data.get("status", "")
                now = time.monotonic()

                # Show progress bar for download
                if "completed" in data and "total" in data and show_progress:
                    completed = data["completed"]
                    total = data["total"]
                    if total > 0 and now - last_update > 0.3:
                        pct = completed / total * 100
                        bar_width = 30
                        filled = int(bar_width * completed / total)
                        bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
                        size_mb = total / (1024 * 1024)
                        done_mb = completed / (1024 * 1024)
                        sys.stdout.write(f"\r  {bar} {pct:5.1f}%  ({done_mb:.0f}/{size_mb:.0f} MB)  {status}")
                        sys.stdout.flush()
                        last_update = now
                elif status != last_status and show_progress:
                    if last_status:
                        sys.stdout.write("\n")
                    sys.stdout.write(f"  {status}")
                    sys.stdout.flush()
                    last_status = status

            if show_progress:
                sys.stdout.write("\n")
                click.echo()
                click.echo(click.style("  Model ready!", fg="green", bold=True))
                click.echo()

        return True

    except httpx.ConnectError:
        if show_progress:
            click.echo(click.style("\n  Error: Cannot connect to Ollama.", fg="red"))
            click.echo("  Make sure Ollama is running: ollama serve")
        return False
    except Exception as e:
        if show_progress:
            click.echo(click.style(f"\n  Error pulling model: {e}", fg="red"))
        return False


def ensure_model(model: str = DEFAULT_MODEL, show_progress: bool = True) -> bool:
    """Ensure a model is available, pulling it if needed.

    Returns True if the model is ready, False on failure.
    """
    if is_model_available(model):
        return True
    return pull_model(model, show_progress=show_progress)


def setup_ollama_judge(
    model: str = DEFAULT_MODEL,
) -> tuple[str, str, str]:
    """Return (judge_uri, judge_model, api_key) for Ollama as judge.

    The OpenAI-compat judge connects to Ollama's /v1 endpoint.
    Ollama doesn't need an API key, but the field can't be empty.
    """
    return (
        f"openai-compat://{OLLAMA_OPENAI_URL}",
        model,
        "ollama",  # Placeholder — Ollama ignores auth
    )
