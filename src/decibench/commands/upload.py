"""CLI command: decibench upload-audio."""

from __future__ import annotations

from pathlib import Path

import click

from decibench.importers.audio import AudioImporter
from decibench.store import get_store


@click.command(name="upload-audio")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--agent", default="", help="Agent name/identifier.")
@click.option("--diarize", is_flag=True, help="Run speaker diarization.")
@click.option("--evaluate", is_flag=True, help="Run evaluation immediately after upload.")
@click.option("--suite", default="quick", help="Suite to evaluate against.")
@click.option("--mode", default="semantic", help="Evaluation mode.")
@click.pass_context
def upload_audio(
    ctx: click.Context,
    file: Path,
    agent: str,
    diarize: bool,
    evaluate: bool,
    suite: str,
    mode: str,
) -> None:
    """Upload a call audio file to Decibench for analysis."""
    from decibench.config import load_config

    config = load_config()
    importer = AudioImporter(config)

    import asyncio

    async def _run() -> None:
        trace = await importer.import_file(
            file,
            source="cli_upload",
            agent_name=agent,
            diarize=diarize,
        )
        store = get_store()
        store.save_call_trace(trace)

        click.echo(f"✓ Imported call {trace.id}")
        click.echo(f"  Duration: {trace.duration_ms:.0f} ms")
        click.echo(f"  Segments: {len(trace.transcript)}")

        if evaluate:
            from decibench.orchestrator import Orchestrator

            orch = Orchestrator(config)
            result = await orch.evaluate_trace(trace, suite=suite, mode=mode)
            store.save_call_evaluation(trace, result)

            click.echo(f"\n  Score: {result.score:.1f}/100")
            click.echo(f"  Passed: {'✓' if result.passed else '✗'}")
            if result.failures:
                click.echo("  Failures:")
                for f in result.failures:
                    click.echo(f"    - {f}")

    asyncio.run(_run())
