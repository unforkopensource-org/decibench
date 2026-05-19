"""SQLite-backed RAG corpus store.

Schema v4 adds two tables alongside the existing runs/calls stores:

    rag_documents (id, source_path, title, mime_type, ingested_at, bytes,
                   embedding_provider, sha256)
    rag_chunks    (id, document_id, ordinal, text, embedding BLOB,
                   metadata JSON)

Re-ingesting the same file (same sha256) is a no-op — the document id IS
the sha256 of the file content. Removing a document cascades to its chunks.

The store holds raw numpy float32 buffers in the ``embedding`` BLOB column.
No vector-index extension required — at our scale (≤ 100k chunks) a
pure-Python cosine k-NN is fast enough, and we keep the dependency surface
small. The interface is abstracted so a vector-DB backend can swap in later.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from decibench.store.sqlite import default_store_path

if TYPE_CHECKING:
    from collections.abc import Iterator

    import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------- public dataclasses


@dataclass
class StoredDocument:
    id: str
    source_path: str
    title: str
    mime_type: str
    ingested_at: str
    bytes: int
    embedding_provider: str
    sha256: str
    chunk_count: int


@dataclass
class StoredChunk:
    id: str
    document_id: str
    ordinal: int
    text: str
    embedding: np.ndarray
    metadata: dict[str, Any]


# ---------------------------------------------------------- the store


class RagStore:
    """Read/write the RAG corpus persisted in the local SQLite store.

    Uses the same database file as ``RunStore`` so users don't have to
    manage two locations. Migrations are owned by
    ``decibench.store.migrations`` (v4 adds rag_documents / rag_chunks).
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_store_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Trigger migrations by opening a RunStore once. RunStore.__init__
        # is idempotent + cheap.
        from decibench.store.sqlite import RunStore  # late import — avoid cycle

        RunStore(self.path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -------------------------------------------------------- mutations

    def upsert_document(
        self,
        *,
        source_path: str,
        title: str,
        mime_type: str,
        content: str,
        embedding_provider: str,
    ) -> str:
        """Idempotent insert. Document id = sha256(content).

        Returns the document id whether or not it was already present.
        """
        sha = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
        ingested_at = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            existing = conn.execute("SELECT id FROM rag_documents WHERE id = ?", (sha,)).fetchone()
            if existing:
                return sha
            conn.execute(
                """
                INSERT INTO rag_documents (
                    id, source_path, title, mime_type, ingested_at, bytes,
                    embedding_provider, sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sha,
                    source_path,
                    title or Path(source_path).name,
                    mime_type,
                    ingested_at,
                    len(content.encode("utf-8")),
                    embedding_provider,
                    sha,
                ),
            )
        return sha

    def write_chunks(
        self,
        document_id: str,
        chunks: list[tuple[str, dict[str, Any], np.ndarray]],
    ) -> int:
        """Replace any existing chunks for the document, then write new ones.

        Each chunk is ``(text, metadata_dict, embedding_vector)``. The
        embedding is stored as raw float32 bytes; the dim is recovered from
        the document's embedding_provider at read time (or from the chunk
        metadata, which we also stash dim into).
        """
        import numpy as np

        with self._connect() as conn:
            conn.execute("DELETE FROM rag_chunks WHERE document_id = ?", (document_id,))
            for ordinal, (text, metadata, vec) in enumerate(chunks):
                vec32 = np.ascontiguousarray(vec, dtype=np.float32)
                meta = dict(metadata)
                meta["dim"] = int(vec32.shape[0])
                conn.execute(
                    """
                    INSERT INTO rag_chunks (
                        id, document_id, ordinal, text, embedding, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{document_id}-{ordinal:05d}",
                        document_id,
                        ordinal,
                        text,
                        vec32.tobytes(),
                        json.dumps(meta, sort_keys=True),
                    ),
                )
        return len(chunks)

    def remove_document(self, document_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM rag_documents WHERE id = ?", (document_id,))
            # ON DELETE CASCADE handles chunks
            return cur.rowcount > 0

    def remove_all(self) -> int:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM rag_documents")
            return cur.rowcount

    # -------------------------------------------------------- reads

    def list_documents(self) -> list[StoredDocument]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT d.id, d.source_path, d.title, d.mime_type, d.ingested_at,
                       d.bytes, d.embedding_provider, d.sha256,
                       (SELECT COUNT(*) FROM rag_chunks c WHERE c.document_id = d.id) AS chunk_count
                FROM rag_documents d
                ORDER BY ingested_at DESC
                """
            ).fetchall()
        return [
            StoredDocument(
                id=r["id"],
                source_path=r["source_path"],
                title=r["title"],
                mime_type=r["mime_type"],
                ingested_at=r["ingested_at"],
                bytes=r["bytes"],
                embedding_provider=r["embedding_provider"],
                sha256=r["sha256"],
                chunk_count=r["chunk_count"],
            )
            for r in rows
        ]

    def get_document(self, document_id: str) -> StoredDocument | None:
        for d in self.list_documents():
            if d.id == document_id:
                return d
        return None

    def iter_chunks(self, *, document_id: str | None = None) -> Iterator[StoredChunk]:
        import numpy as np

        with self._connect() as conn:
            if document_id is not None:
                rows = conn.execute(
                    """
                    SELECT id, document_id, ordinal, text, embedding, metadata
                    FROM rag_chunks
                    WHERE document_id = ?
                    ORDER BY ordinal
                    """,
                    (document_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, document_id, ordinal, text, embedding, metadata
                    FROM rag_chunks
                    ORDER BY document_id, ordinal
                    """,
                ).fetchall()

        for r in rows:
            meta = json.loads(r["metadata"])
            dim = int(meta.get("dim", 0)) or None
            buf = r["embedding"]
            if dim:
                vec = np.frombuffer(buf, dtype=np.float32, count=dim).copy()
            else:
                vec = np.frombuffer(buf, dtype=np.float32).copy()
            yield StoredChunk(
                id=r["id"],
                document_id=r["document_id"],
                ordinal=r["ordinal"],
                text=r["text"],
                embedding=vec,
                metadata=meta,
            )

    def chunk_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM rag_chunks").fetchone()
        return int(row["n"])

    def stats(self) -> dict[str, Any]:
        docs = self.list_documents()
        return {
            "documents": len(docs),
            "chunks": self.chunk_count(),
            "bytes": sum(d.bytes for d in docs),
            "providers": sorted({d.embedding_provider for d in docs}),
            "store_path": str(self.path),
        }
