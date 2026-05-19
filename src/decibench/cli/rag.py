"""decibench rag — knowledge corpus + scenario synthesis.

Six subcommands, all backed by ``decibench.rag``:

    ingest      Add files / directories / pasted text to the local corpus.
    list        Show ingested documents + chunk counts.
    search      Debug retrieval: top-K chunks for a query.
    synthesize  Generate scenarios from the corpus + a topic.
    remove      Delete a document (or wipe the corpus with --all).
    info        Corpus stats + active embedding provider.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from decibench.config import load_config
from decibench.rag import (
    RagStore,
    ingest_paths,
    ingest_text,
    retrieve,
    synthesize_scenarios,
)
from decibench.rag.embed import CloudEgressForbidden


@click.group("rag")
def rag_cmd() -> None:
    """Manage the local RAG corpus and synthesize domain scenarios."""


# ----------------------------------------------------------- ingest


@rag_cmd.command("ingest")
@click.argument("paths", nargs=-1, type=click.Path(path_type=Path))
@click.option("--text", "text_input", default=None,
              help="Pasted text to ingest (alternative to file paths).")
@click.option("--title", default="pasted-snippet",
              help="Title for --text ingest (ignored when files given).")
@click.option("--cloud-confirm", is_flag=True, default=False,
              help="Explicit acknowledgement that cloud embedding is OK.")
def rag_ingest_cmd(
    paths: tuple[Path, ...],
    text_input: str | None,
    title: str,
    cloud_confirm: bool,
) -> None:
    """Ingest files or directories into the local RAG store.

    Defaults: local-only embedding, no cloud egress. Re-ingesting the same
    file (same sha256) is a no-op.
    """
    config = load_config()
    rag_cfg = config.rag
    allow_cloud = rag_cfg.allow_cloud or cloud_confirm

    if not paths and not text_input:
        raise click.ClickException(
            "Pass one or more file/dir paths, or use --text \"...\". Nothing to ingest."
        )

    store = RagStore()
    try:
        if text_input is not None:
            result = ingest_text(
                text=text_input,
                title=title,
                store=store,
                embedder_uri=rag_cfg.embedding,
                allow_cloud=allow_cloud,
                target_tokens=rag_cfg.chunk_size_tokens,
                overlap_tokens=rag_cfg.chunk_overlap_tokens,
            )
        else:
            result = ingest_paths(
                list(paths),
                store=store,
                embedder_uri=rag_cfg.embedding,
                allow_cloud=allow_cloud,
                target_tokens=rag_cfg.chunk_size_tokens,
                overlap_tokens=rag_cfg.chunk_overlap_tokens,
            )
    except CloudEgressForbidden as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Embedder:     {result.embedding_provider}")
    click.echo(f"Added:        {result.documents_added} documents, {result.chunks_added} chunks")
    if result.documents_skipped:
        click.echo(f"Skipped:      {result.documents_skipped} (already in store)")
    if result.failures:
        click.echo(click.style(f"Failures:     {len(result.failures)}", fg="yellow"))
        for f in result.failures:
            click.echo(f"  {f['path']}: {f['error']}")


# ----------------------------------------------------------- list


@rag_cmd.command("list")
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON.")
def rag_list_cmd(as_json: bool) -> None:
    """Show ingested documents and chunk counts."""
    docs = RagStore().list_documents()
    if as_json:
        click.echo(json.dumps([d.__dict__ for d in docs], indent=2, default=str))
        return
    if not docs:
        click.echo("Corpus is empty. Try: decibench rag ingest <files>")
        return
    click.echo(f"{'id (sha256[:12])':<14}  {'chunks':>6}  {'bytes':>8}  embed_provider           title")
    for d in docs:
        click.echo(
            f"{d.id[:12]}  {d.chunk_count:>6}  {d.bytes:>8}  "
            f"{d.embedding_provider[:23]:<23}  {d.title}"
        )


# ----------------------------------------------------------- search


@rag_cmd.command("search")
@click.argument("query")
@click.option("-k", "top_k", default=5, type=int, help="Number of hits.")
@click.option("--json", "as_json", is_flag=True, default=False)
def rag_search_cmd(query: str, top_k: int, as_json: bool) -> None:
    """Debug retrieval — show the chunks RAG would surface for a query."""
    config = load_config()
    try:
        hits = retrieve(
            query,
            k=top_k,
            embedder_uri=config.rag.embedding,
            allow_cloud=config.rag.allow_cloud,
        )
    except CloudEgressForbidden as exc:
        raise click.ClickException(str(exc)) from exc

    if as_json:
        click.echo(json.dumps([h.__dict__ for h in hits], indent=2))
        return
    if not hits:
        click.echo("No results. Corpus may be empty — try `decibench rag list`.")
        return
    for h in hits:
        click.echo(f"\n[{h.score:.3f}] {' > '.join(h.section_path) or '(top)'}")
        click.echo(f"  doc={h.document_id[:12]}  chunk={h.chunk_id}")
        click.echo("  " + h.text[:280].replace("\n", " "))


# ----------------------------------------------------------- synthesize


@rag_cmd.command("synthesize")
@click.option("--topic", multiple=True,
              help="Topic to cover (repeat for multiple). If omitted, uses a default 8-topic set.")
@click.option("--suite", default="custom-rag", help="Suite slug to write under.")
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Where to write the synthesized scenarios.",
)
@click.option("--count", type=int, default=None,
              help="Cap the number of topics actually synthesized (default: all).")
def rag_synthesize_cmd(
    topic: tuple[str, ...],
    suite: str,
    out_dir: Path | None,
    count: int | None,
) -> None:
    """Synthesize Decibench scenarios from the local RAG corpus.

    Three validation gates run on each synthesized scenario (schema,
    grounding, safety). Only scenarios that pass all three are written.
    """
    config = load_config()
    rag_cfg = config.rag
    store = RagStore()
    if store.chunk_count() == 0:
        raise click.ClickException(
            "Corpus is empty. Ingest something first: decibench rag ingest <files>"
        )

    if not config.has_judge:
        raise click.ClickException(
            "Synthesis needs an LLM. Configure a judge first:\n"
            "  decibench models preset ollama balanced     (free, local)\n"
            "  decibench auth set openai && decibench models preset openai balanced"
        )

    # Build the topic list — user-supplied or fall back to defaults.
    if topic:
        topics = [
            {
                "id_slug": _slugify(t)[:40] or f"topic-{i}",
                "intent": t,
                "tags": "rag,custom",
                "criterion": f"Agent handles: {t}",
            }
            for i, t in enumerate(topic, start=1)
        ]
    else:
        from decibench.rag.synthesize import DEFAULT_TOPICS

        topics = list(DEFAULT_TOPICS)

    if count is not None:
        topics = topics[: max(1, count)]

    if out_dir is None:
        from importlib import resources
        # Default: write under the packaged suites tree so the loader picks it up.
        suite_pkg = resources.files("decibench.scenarios.suites")
        out_dir = Path(str(suite_pkg)) / suite

    click.echo(f"Synthesizing {len(topics)} scenarios via "
               f"{config.providers.judge}/{config.providers.judge_model} → {out_dir}")

    result = synthesize_scenarios(
        topics=topics,
        suite=suite,
        out_dir=out_dir,
        judge_uri=config.providers.judge,
        judge_model=config.providers.judge_model,
        judge_api_key=config.providers.judge_api_key,
        store=store,
        embedder_uri=rag_cfg.embedding,
        grounding_threshold=rag_cfg.grounding_threshold,
    )

    click.echo(f"\nAccepted: {len(result.accepted)}    Rejected: {len(result.rejected)}")
    for a in result.accepted:
        click.echo(f"  ✓ {a['scenario_id']}   grounding={a['grounding_score']:.2f}")
    for r in result.rejected:
        click.echo(click.style(f"  ✗ {r['topic']}: {r['reason']}", fg="yellow"))


# ----------------------------------------------------------- remove


@rag_cmd.command("remove")
@click.option("--document-id", default=None, help="Remove one document by id (or prefix).")
@click.option("--all", "remove_all", is_flag=True, default=False,
              help="Wipe the entire RAG corpus.")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation.")
def rag_remove_cmd(document_id: str | None, remove_all: bool, yes: bool) -> None:
    """Remove a document (or wipe the corpus)."""
    store = RagStore()
    if remove_all:
        if not yes:
            click.confirm("Delete EVERY document and chunk in the corpus?", abort=True)
        n = store.remove_all()
        click.echo(f"Removed {n} documents.")
        return
    if not document_id:
        raise click.ClickException("Pass --document-id <id> or --all.")
    # Allow id prefix
    docs = [d for d in store.list_documents() if d.id.startswith(document_id)]
    if not docs:
        raise click.ClickException(f"No document matches id prefix {document_id!r}.")
    if len(docs) > 1:
        raise click.ClickException(
            f"Prefix {document_id!r} matches {len(docs)} documents — pass a longer prefix."
        )
    store.remove_document(docs[0].id)
    click.echo(f"Removed: {docs[0].id[:12]}  {docs[0].title}")


# ----------------------------------------------------------- info


@rag_cmd.command("info")
def rag_info_cmd() -> None:
    """Corpus statistics + active embedding provider."""
    config = load_config()
    stats = RagStore().stats()
    click.echo(f"Store path:           {stats['store_path']}")
    click.echo(f"Documents:            {stats['documents']}")
    click.echo(f"Chunks:               {stats['chunks']}")
    click.echo(f"Bytes:                {stats['bytes']}")
    click.echo(f"Embedding providers:  {', '.join(stats['providers']) or '(none yet)'}")
    click.echo(f"Configured embedder:  {config.rag.embedding}")
    click.echo(f"Cloud egress:         {'allowed' if config.rag.allow_cloud else 'OFF (local only)'}")


# ----------------------------------------------------------- helpers


def _slugify(s: str) -> str:
    import re

    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")
