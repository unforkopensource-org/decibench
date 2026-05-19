"""k-NN retrieval over stored chunks.

Pure-Python cosine similarity. At our scale (≤100k chunks) this comfortably
finishes in under 100ms with numpy. For larger corpora the interface stays
the same and we swap in a vector-DB backend without changing call sites.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from decibench.rag.embed import DEFAULT_EMBEDDER_URI, Embedder, get_embedder
from decibench.rag.store import RagStore


@dataclass
class RetrievalHit:
    chunk_id: str
    document_id: str
    text: str
    score: float  # cosine similarity in [-1, 1]; normalized embs → [0, 1]
    section_path: list[str]
    metadata: dict[str, Any]


def retrieve(
    query: str,
    *,
    k: int = 5,
    store: RagStore | None = None,
    embedder: Embedder | None = None,
    embedder_uri: str = DEFAULT_EMBEDDER_URI,
    allow_cloud: bool = False,
    api_key: str = "",
    document_filter: list[str] | None = None,
) -> list[RetrievalHit]:
    """Return the top-K chunks by cosine similarity to ``query``.

    Args:
        query: natural-language search.
        k: number of hits to return.
        store: optional pre-constructed store.
        embedder: optional pre-constructed embedder (must match what was
            used to ingest the corpus, otherwise scores are meaningless).
        embedder_uri: fallback if no embedder passed.
        document_filter: restrict search to specific document ids.
    """
    import numpy as np

    s = store or RagStore()
    if s.chunk_count() == 0:
        return []
    em = embedder or get_embedder(embedder_uri, allow_cloud=allow_cloud, api_key=api_key)

    chunks = [c for c in s.iter_chunks() if not document_filter or c.document_id in document_filter]
    if not chunks:
        return []

    # Stack embeddings, embed the query, dot-product.
    mat = np.stack([c.embedding for c in chunks]).astype(np.float32)
    q = em.embed([query])[0].astype(np.float32)
    # Both already normalized at ingest/query time; cosine == dot.
    scores = mat @ q
    order = np.argsort(-scores)[: max(1, k)]

    return [
        RetrievalHit(
            chunk_id=chunks[i].id,
            document_id=chunks[i].document_id,
            text=chunks[i].text,
            score=float(scores[i]),
            section_path=list(chunks[i].metadata.get("section_path", [])),
            metadata=dict(chunks[i].metadata),
        )
        for i in order
    ]
