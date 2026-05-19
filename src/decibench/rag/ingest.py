"""Ingestion pipeline: file/dir/text → chunks → embeddings → store.

Chunking strategy: structural-aware.

- Markdown: split on H1/H2/H3 boundaries, then sub-chunk by token window.
- Plain text: recursive split into ~800-token windows with 100-token overlap.
- (Plus future support for .pdf, .docx — these raise ``UnsupportedMimeType``
  in v1 with a clean error rather than ingesting garbage.)

Each chunk carries ``metadata.section_path`` so retrieval can surface where
in the document a hit came from.
"""

from __future__ import annotations

import logging
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from decibench.rag.embed import DEFAULT_EMBEDDER_URI, Embedder, get_embedder
from decibench.rag.store import RagStore

logger = logging.getLogger(__name__)


SUPPORTED_TEXT_MIMES: frozenset[str] = frozenset(
    {
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "application/x-markdown",
        "text/html",
        "application/json",
    }
)
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".txt",
        ".md",
        ".markdown",
        ".mdown",
        ".rst",
    }
)


class UnsupportedMimeType(Exception):
    """Raised when an ingest file's type isn't on the v1 allowlist."""


@dataclass
class IngestResult:
    """Summary of one ingest call (CLI, MCP, or API surface)."""

    documents_added: int = 0
    documents_skipped: int = 0  # already in store (idempotent)
    chunks_added: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    embedding_provider: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "documents_added": self.documents_added,
            "documents_skipped": self.documents_skipped,
            "chunks_added": self.chunks_added,
            "failures": list(self.failures),
            "document_ids": list(self.document_ids),
            "embedding_provider": self.embedding_provider,
        }


# ---------------------------------------------------------------- chunking


_TOKEN_RE = re.compile(r"\S+")


def _approx_token_count(text: str) -> int:
    """Token estimate: count whitespace-separated runs. Cheap, good enough."""
    return len(_TOKEN_RE.findall(text))


def _split_markdown_by_heading(text: str) -> list[tuple[list[str], str]]:
    """Return (section_path, body) tuples — section_path is the heading stack."""
    sections: list[tuple[list[str], str]] = []
    stack: list[str] = []
    buf: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if m:
            if buf:
                sections.append((list(stack), "\n".join(buf).strip()))
                buf = []
            level = len(m.group(1))
            title = m.group(2)
            # Maintain a heading stack truncated to current level
            stack = stack[: level - 1] + [title]
            continue
        buf.append(line)
    if buf:
        sections.append((list(stack), "\n".join(buf).strip()))
    return [(p, b) for p, b in sections if b]


def _chunk_body(
    body: str,
    *,
    target_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """Greedy paragraph packer with token-based overlap."""
    if not body.strip():
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    chunks: list[str] = []
    cur: list[str] = []
    cur_tokens = 0
    for para in paragraphs:
        ptoks = _approx_token_count(para)
        if cur and cur_tokens + ptoks > target_tokens:
            chunks.append("\n\n".join(cur))
            # Build overlap: pull paragraphs from the tail until we hit the budget.
            tail_tokens = 0
            tail: list[str] = []
            for p in reversed(cur):
                tail.insert(0, p)
                tail_tokens += _approx_token_count(p)
                if tail_tokens >= overlap_tokens:
                    break
            cur = list(tail)
            cur_tokens = tail_tokens
        cur.append(para)
        cur_tokens += ptoks
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def chunk_text(
    text: str,
    *,
    mime: str = "text/markdown",
    target_tokens: int = 800,
    overlap_tokens: int = 100,
) -> list[tuple[str, dict[str, Any]]]:
    """Public chunker — returns (chunk_text, metadata) pairs.

    Markdown gets structural awareness; everything else gets plain windowing.
    """
    text = text.strip()
    if not text:
        return []

    if mime in ("text/markdown", "text/x-markdown", "application/x-markdown"):
        out: list[tuple[str, dict[str, Any]]] = []
        for section_path, body in _split_markdown_by_heading(text):
            for chunk in _chunk_body(body, target_tokens=target_tokens, overlap_tokens=overlap_tokens):
                out.append((chunk, {"section_path": section_path}))
        return out

    # Plain text / unknown: window the whole body.
    return [
        (chunk, {"section_path": []})
        for chunk in _chunk_body(text, target_tokens=target_tokens, overlap_tokens=overlap_tokens)
    ]


# ---------------------------------------------------------------- public API


def _detect_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    if mime:
        return mime
    if path.suffix.lower() in (".md", ".markdown", ".mdown"):
        return "text/markdown"
    if path.suffix.lower() == ".txt":
        return "text/plain"
    return "application/octet-stream"


def _check_supported(path: Path, mime: str) -> None:
    if path.suffix.lower() in SUPPORTED_EXTENSIONS:
        return
    if mime in SUPPORTED_TEXT_MIMES:
        return
    raise UnsupportedMimeType(
        f"{path.name}: mime {mime!r} not in v1 allowlist. Supported today: "
        f"{sorted(SUPPORTED_EXTENSIONS)} + text mime types. PDF / DOCX are planned."
    )


def ingest_text(
    *,
    text: str,
    title: str = "pasted-snippet",
    store: RagStore | None = None,
    embedder_uri: str = DEFAULT_EMBEDDER_URI,
    embedder: Embedder | None = None,
    allow_cloud: bool = False,
    api_key: str = "",
    target_tokens: int = 800,
    overlap_tokens: int = 100,
) -> IngestResult:
    """Ingest a single string. The dashboard's paste-text path lands here."""
    result = IngestResult()
    s = store or RagStore()
    em = embedder or get_embedder(embedder_uri, allow_cloud=allow_cloud, api_key=api_key)
    result.embedding_provider = em.name

    chunks = chunk_text(
        text,
        mime="text/markdown" if "#" in text[:200] else "text/plain",
        target_tokens=target_tokens,
        overlap_tokens=overlap_tokens,
    )
    if not chunks:
        result.failures.append({"path": title, "error": "no non-empty chunks produced"})
        return result

    doc_id = s.upsert_document(
        source_path=f"paste:{title}",
        title=title,
        mime_type="text/markdown",
        content=text,
        embedding_provider=em.name,
    )
    # If the doc already existed AND already has chunks for this embedder, skip.
    existing = s.get_document(doc_id)
    if existing and existing.chunk_count > 0 and existing.embedding_provider == em.name:
        result.documents_skipped += 1
        result.document_ids.append(doc_id)
        return result

    texts = [c for c, _ in chunks]
    metas = [m for _, m in chunks]
    vectors = em.embed(texts)
    written = s.write_chunks(
        doc_id,
        [(texts[i], metas[i], vectors[i]) for i in range(len(texts))],
    )
    result.documents_added += 1
    result.chunks_added += written
    result.document_ids.append(doc_id)
    return result


def ingest_paths(
    paths: list[Path],
    *,
    store: RagStore | None = None,
    embedder_uri: str = DEFAULT_EMBEDDER_URI,
    embedder: Embedder | None = None,
    allow_cloud: bool = False,
    api_key: str = "",
    target_tokens: int = 800,
    overlap_tokens: int = 100,
    recurse: bool = True,
) -> IngestResult:
    """Ingest a list of files/dirs. Directories are walked recursively.

    Per-file failures don't abort the batch — they're recorded in
    ``IngestResult.failures`` with a path and reason.
    """
    result = IngestResult()
    s = store or RagStore()
    em = embedder or get_embedder(embedder_uri, allow_cloud=allow_cloud, api_key=api_key)
    result.embedding_provider = em.name

    files: list[Path] = []
    for p in paths:
        if p.is_dir() and recurse:
            files.extend(sorted(q for q in p.rglob("*") if q.is_file()))
        elif p.is_file():
            files.append(p)
        else:
            result.failures.append({"path": str(p), "error": "not a file or directory"})

    for path in files:
        try:
            mime = _detect_mime(path)
            _check_supported(path, mime)
            text = path.read_text(encoding="utf-8", errors="replace")
        except UnsupportedMimeType as exc:
            result.failures.append({"path": str(path), "error": str(exc)})
            continue
        except OSError as exc:
            result.failures.append({"path": str(path), "error": f"read error: {exc}"})
            continue

        chunks = chunk_text(
            text,
            mime=mime,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
        )
        if not chunks:
            result.failures.append({"path": str(path), "error": "no non-empty chunks"})
            continue

        doc_id = s.upsert_document(
            source_path=str(path),
            title=path.stem,
            mime_type=mime,
            content=text,
            embedding_provider=em.name,
        )
        existing = s.get_document(doc_id)
        if existing and existing.chunk_count > 0 and existing.embedding_provider == em.name:
            result.documents_skipped += 1
            result.document_ids.append(doc_id)
            continue

        texts = [c for c, _ in chunks]
        metas = [m for _, m in chunks]
        try:
            vectors = em.embed(texts)
        except Exception as exc:
            result.failures.append({"path": str(path), "error": f"embed: {exc}"})
            continue
        written = s.write_chunks(
            doc_id,
            [(texts[i], metas[i], vectors[i]) for i in range(len(texts))],
        )
        result.documents_added += 1
        result.chunks_added += written
        result.document_ids.append(doc_id)

    return result
