"""Embedding providers — URI-keyed, same pattern as judges.

The RAG store doesn't care HOW vectors are produced. It calls
``get_embedder(uri)`` and gets back an object with ``embed(texts) -> array``.
That object can be a local sentence-transformers model, an OpenAI-compat
endpoint, an Ollama model — whatever resolves the URI scheme.

Default: ``embed://local/all-MiniLM-L6-v2`` — small (~80 MB), CPU-friendly,
384-dim. Pulled lazily on first use, cached at the location
sentence-transformers picks.

Cloud egress is OFF by default. Cloud schemes raise
``CloudEgressForbidden`` unless ``[rag] allow_cloud = true`` is set or
``allow_cloud=True`` is passed explicitly. ``decibench doctor`` reports
the current state.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)


class CloudEgressForbidden(Exception):
    """Raised when a cloud embedder is requested but allow_cloud is false."""


@runtime_checkable
class Embedder(Protocol):
    """Stateless-ish callable that turns text into a fixed-dim vector."""

    @property
    def name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return a (N, dim) float32 array; one row per input string."""
        ...


# --------------------------------------------------------------- providers


class LocalSentenceTransformerEmbedder:
    """sentence-transformers / Hugging Face local model.

    The first call downloads the model into the HF cache; subsequent calls
    are fast. We import sentence-transformers inside ``embed()`` so the
    import cost only hits users who actually use RAG.
    """

    cloud = False

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: Any | None = None
        self._dim: int | None = None

    @property
    def name(self) -> str:
        return f"local/{self._model_name}"

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._load()
        assert self._dim is not None
        return self._dim

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Local RAG embedding needs sentence-transformers. Install with "
                "`pip install decibench[rag]` or `pip install sentence-transformers`."
            ) from exc
        logger.info("Loading sentence-transformers model: %s", self._model_name)
        self._model = SentenceTransformer(self._model_name)
        self._dim = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> np.ndarray:
        import numpy as np

        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        self._load()
        assert self._model is not None
        vecs = self._model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vecs.astype(np.float32)


class HashEmbedder:
    """Deterministic non-ML embedder for tests + the no-numpy fallback path.

    Hashes each text into a fixed-dim float vector. Useless for retrieval
    quality but fast, dependency-free, and produces *stable* embeddings so
    tests can assert exact retrieval order.
    """

    cloud = False

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim

    @property
    def name(self) -> str:
        return f"hash/dim={self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> np.ndarray:
        import numpy as np

        out = np.zeros((len(texts), self._dim), dtype=np.float32)
        for i, text in enumerate(texts):
            # SHA-256 chunked into bytes → seeded normal-ish vector.
            seed = hashlib.sha256(text.encode("utf-8")).digest()
            # Repeat the digest to fill `dim` floats.
            buf = (seed * ((self._dim * 4) // len(seed) + 1))[: self._dim * 4]
            arr = np.frombuffer(buf, dtype=np.uint8).astype(np.float32)
            arr = (arr - 127.5) / 127.5  # map to roughly [-1, 1]
            arr = arr[: self._dim]
            n = np.linalg.norm(arr)
            if n > 0:
                arr = arr / n
            out[i] = arr
        return out


class OpenAICompatEmbedder:
    """OpenAI-compatible /v1/embeddings endpoint.

    Cloud-egress provider. Refuses to instantiate unless ``allow_cloud``.
    """

    cloud = True

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        allow_cloud: bool = False,
    ) -> None:
        if not allow_cloud:
            raise CloudEgressForbidden(
                f"Embedding provider {base_url!r} would send your documents to a "
                "cloud service, but [rag] allow_cloud is not enabled. Set "
                "allow_cloud=true in decibench.toml [rag] or pass --cloud-confirm."
            )
        self._base = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._dim_cache: int | None = None

    @property
    def name(self) -> str:
        return f"openai-compat/{self._model}"

    @property
    def dim(self) -> int:
        if self._dim_cache is None:
            # Probe with one tiny embedding to learn the dim.
            vec = self.embed(["probe"])
            self._dim_cache = vec.shape[1]
        return self._dim_cache

    def embed(self, texts: list[str]) -> np.ndarray:
        import httpx
        import numpy as np

        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        payload = {"model": self._model, "input": texts}
        with httpx.Client(timeout=60.0) as c:
            r = c.post(f"{self._base}/embeddings", json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        rows = [d["embedding"] for d in data["data"]]
        arr = np.asarray(rows, dtype=np.float32)
        # Normalize so cosine similarity == dot product later.
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms


# --------------------------------------------------------------- resolver

DEFAULT_EMBEDDER_URI = "embed://local/all-MiniLM-L6-v2"


def get_embedder(
    uri: str = DEFAULT_EMBEDDER_URI, *, allow_cloud: bool = False, api_key: str = ""
) -> Embedder:
    """Resolve an embedder URI to a concrete provider.

    URI schemes:
        embed://local/<model>            — sentence-transformers, local CPU
        embed://hash/<dim>               — deterministic hash embedder (tests)
        embed://ollama/<model>           — Ollama /v1/embeddings (local)
        embed://openai-compat/<model>?base=<url>
    """
    if not uri.startswith("embed://"):
        raise ValueError(f"Embedder URI must start with embed://, got {uri!r}")
    rest = uri[len("embed://") :]
    scheme, _, tail = rest.partition("/")

    if scheme == "local":
        return LocalSentenceTransformerEmbedder(tail or "all-MiniLM-L6-v2")
    if scheme == "hash":
        try:
            return HashEmbedder(dim=int(tail) if tail else 384)
        except ValueError as exc:
            raise ValueError(f"Bad hash embedder dim {tail!r}") from exc
    if scheme == "ollama":
        # Treat as openai-compat against Ollama's local endpoint. Local =
        # not cloud, even though the embedder class is the same shape.
        return _ollama_embedder(model=tail or "nomic-embed-text", api_key=api_key)
    if scheme == "openai-compat":
        # Split off ?base=...
        model, _, query = tail.partition("?")
        base_url = ""
        if query:
            for kv in query.split("&"):
                if kv.startswith("base="):
                    base_url = kv[len("base=") :]
        if not base_url:
            base_url = "https://api.openai.com/v1"
        return OpenAICompatEmbedder(
            base_url=base_url,
            model=model or "text-embedding-3-small",
            api_key=api_key,
            allow_cloud=allow_cloud,
        )
    raise ValueError(f"Unknown embedder scheme {scheme!r} in {uri!r}")


def _ollama_embedder(*, model: str, api_key: str) -> Embedder:
    """Build an OpenAI-compat client pointed at Ollama. Local, no cloud gate."""
    # Reuse OpenAICompatEmbedder but bypass the cloud guard since Ollama is local.
    em = OpenAICompatEmbedder.__new__(OpenAICompatEmbedder)
    em._base = "http://localhost:11434/v1"
    em._model = model
    em._api_key = api_key
    em._dim_cache = None
    em.cloud = False  # type: ignore[misc]
    return em
