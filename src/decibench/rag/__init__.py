"""Decibench RAG — domain-aware scenario synthesis.

Five primitives, one backend:

- ``store``     SQLite-backed corpus (documents + chunked embeddings)
- ``embed``     pluggable embedding providers (local sentence-transformers by default)
- ``ingest``    file/directory/paste-text → chunked + embedded → stored
- ``retrieve``  k-NN over stored embeddings
- ``synthesize`` retrieved chunks + topic → schema-valid Scenario YAML
- ``validate``  three-gate validator (schema, grounding, safety)

CLI (`decibench rag …`), MCP (`rag_*` tools), and the FastAPI workbench
(`/rag/*`) all dispatch through this package. There is one chunker, one
embedding provider table, and one synthesis prompt — no surface keeps a
private copy.
"""

from __future__ import annotations

from decibench.rag.ingest import IngestResult, ingest_paths, ingest_text
from decibench.rag.retrieve import RetrievalHit, retrieve
from decibench.rag.store import RagStore
from decibench.rag.synthesize import SynthesisResult, synthesize_scenarios
from decibench.rag.validate import GateReport, validate_scenario

__all__ = [
    "GateReport",
    "IngestResult",
    "RagStore",
    "RetrievalHit",
    "SynthesisResult",
    "ingest_paths",
    "ingest_text",
    "retrieve",
    "synthesize_scenarios",
    "validate_scenario",
]
