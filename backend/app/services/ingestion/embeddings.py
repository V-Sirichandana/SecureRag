"""Embedding providers behind the :class:`EmbeddingService` protocol.

The application never talks to a provider directly — it asks the factory in
``app.services.rag`` for the configured implementation. Two providers ship:

* ``hashing``   deterministic feature hashing, zero downloads (dev/tests)
* ``fastembed`` local multilingual model, e.g. BAAI/bge-m3 (optional extra)
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re

from app.core.exceptions import ServiceNotConfiguredError
from app.services.rag.base import EmbeddingService

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


class HashingEmbeddingProvider:
    """Deterministic feature-hashing embeddings — no model download.

    Tokens and character trigrams are hashed into a fixed-width signed vector
    that is L2-normalized. Deterministic across processes and platforms, which
    makes it ideal for tests and offline development. Swap ``EMBEDDING_PROVIDER``
    to ``fastembed`` for semantic quality in production.
    """

    def __init__(self, *, dimension: int = 384) -> None:
        if dimension < 8:
            raise ValueError("embedding dimension must be >= 8")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    # -------------------------------------------------------------- internals
    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        normalized = re.sub(r"\s+", " ", text.lower()).strip()
        for feature in self._features(normalized):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return _l2_normalize(vector)

    @staticmethod
    def _features(normalized: str) -> list[str]:
        features: list[str] = []
        for token in _TOKEN_RE.findall(normalized):
            features.append(f"w:{token}")
        # character trigrams keep some signal for scripts without word spaces
        padded = f" {normalized} "
        features.extend(
            f"c:{padded[index:index + 3]}" for index in range(len(padded) - 2)
        )
        return features


class FastEmbedEmbeddingProvider:
    """Local multilingual model through fastembed (optional dependency).

    Install with ``pip install fastembed`` and set ``EMBEDDING_PROVIDER=fastembed``.
    Default model: BAAI/bge-m3 (set ``EMBEDDING_DIM=1024`` to match).
    """

    def __init__(self, *, model: str, dimension: int) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise ServiceNotConfiguredError(
                "SERVICE_NOT_CONFIGURED",
                "EMBEDDING_PROVIDER=fastembed requires the 'fastembed' package "
                "(pip install fastembed).",
            ) from exc
        self._model = TextEmbedding(model_name=model or "BAAI/bge-m3")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = await asyncio.to_thread(
            lambda: [list(map(float, vector)) for vector in self._model.embed(texts)]
        )
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_documents([text])
        return vectors[0]


__all__ = ["EmbeddingService", "FastEmbedEmbeddingProvider", "HashingEmbeddingProvider"]
