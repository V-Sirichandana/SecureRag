"""Reranker providers behind the :class:`~app.services.rag.base.Reranker` protocol.

Two providers ship:

* ``heuristic`` — deterministic offline lexical overlap. Standard library
  only: no model, no network, no API key. It is the default and keeps
  development/tests offline.
* ``fastembed`` — optional local neural cross-encoder (FastEmbed
  ``TextCrossEncoder``). The model is loaded lazily on the first rerank call,
  never at application startup, and is cached per model for reuse.

Both providers only re-order chunks that have already passed the tenant and
CURRENT document-permission checks. The original vector retrieval score is
never overwritten: both scores are kept
(``score`` = original retrieval score, ``rerank_score`` = relevance score).
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import threading
from collections import Counter, OrderedDict
from collections.abc import Callable
from dataclasses import replace
from typing import Any
from unicodedata import normalize as unicodedata_normalize

from app.core.exceptions import AppError, ServiceNotConfiguredError
from app.services.rag import _RERANKERS
from app.services.rag.base import RetrievedChunk
from app.services.rag.retriever import MAX_CANDIDATES

logger = logging.getLogger("securerag.reranker")

PROVIDER_NAME = "heuristic"
DEFAULT_TOP_K = 5

# FastEmbed reranker provider. The provider name is separate from the
# embedding provider so RERANKER_PROVIDER=fastembed never changes embeddings.
FASTEMBED_PROVIDER_NAME = "fastembed"
NEURAL_PROVIDER_NAME = "neural"  # compatibility alias for the same provider
DEFAULT_FASTEMBED_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
FASTEMBED_MIN_VERSION = "0.4.2"

# Bounded process-wide model cache: at most two distinct cross-encoders stay
# resident. Loading happens off the event loop and only on the first rerank.
_MAX_CACHED_MODELS = 2
_MODEL_CACHE: OrderedDict[tuple[Any, str, str | None], Any] = OrderedDict()
_MODEL_CACHE_LOCK = threading.Lock()

# fixed, documented weights — every contribution is bounded so scores stay
# interpretable (0.0 .. 2.5); they are a baseline, not tuned relevance
_WEIGHT_COVERAGE = 1.0
_WEIGHT_FREQUENCY = 0.25
_WEIGHT_PHRASE = 0.75
_WEIGHT_FILENAME = 0.25
_WEIGHT_EXACT_PHRASE = 0.25
_SCORE_PRECISION = 6

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    """NFKC-normalize, case-fold and split into unicode word tokens.

    Punctuation, symbols and underscores separate tokens but never match,
    so mixed case, unicode text and trailing punctuation are handled by the
    same single path.
    """
    normalized = unicodedata_normalize("NFKC", text).casefold()
    return _WORD_RE.findall(normalized)


class HeuristicReranker:
    """Offline lexical implementation of the ``Reranker`` protocol."""

    async def rerank(
        self, *, query: str, chunks: list[RetrievedChunk], top_k: int = DEFAULT_TOP_K
    ) -> list[RetrievedChunk]:
        """Score candidates by lexical overlap and return the best ``top_k``.

        Candidates are copied, never mutated: the vector ``score`` survives
        untouched and each returned copy carries ``rerank_score``. Ties are
        broken deterministically by vector score, then by input position.
        An empty candidate list returns ``[]``; ``top_k`` larger than the
        candidate count returns every candidate.
        """
        self._validate(query=query, top_k=top_k)
        if not chunks:
            return []

        query_tokens = _tokenize(query)
        query_terms = set(query_tokens)
        query_bigrams = list(zip(query_tokens, query_tokens[1:], strict=False))
        query_phrase = " ".join(query_tokens)
        query_frequencies = Counter(query_tokens)

        scored: list[tuple[int, RetrievedChunk, float]] = []
        for position, chunk in enumerate(chunks):
            score = self._score(
                query_terms=query_terms,
                query_bigrams=query_bigrams,
                query_phrase=query_phrase,
                query_frequencies=query_frequencies,
                chunk=chunk,
            )
            scored.append((position, chunk, score))

        scored.sort(key=lambda item: (-item[2], -item[1].score, item[0]))
        return [
            replace(chunk, rerank_score=score) for _, chunk, score in scored[:top_k]
        ]

    # ------------------------------------------------------------- validation
    @staticmethod
    def _validate(*, query: str, top_k: int) -> None:
        """Same conventions as the retriever: domain errors, not HTTP ones."""
        if not (query or "").strip():
            raise AppError("VALIDATION_ERROR", "Search query must not be empty.")
        if top_k < 1:
            raise AppError("VALIDATION_ERROR", "top_k must be at least 1.")

    # -------------------------------------------------------------- scoring
    @staticmethod
    def _score(
        *,
        query_terms: set[str],
        query_bigrams: list[tuple[str, str]],
        query_phrase: str,
        query_frequencies: Counter[str],
        chunk: RetrievedChunk,
    ) -> float:
        """Transparent lexical relevance in ``[0.0, 2.5]``.

        A query with no word tokens (punctuation only) scores 0.0 for every
        candidate, which keeps the vector ranking through the tie-break.
        """
        if not query_terms:
            return 0.0

        chunk_tokens = _tokenize(chunk.text)
        chunk_terms = set(chunk_tokens)
        chunk_frequencies = Counter(chunk_tokens)
        chunk_bigrams = set(zip(chunk_tokens, chunk_tokens[1:], strict=False))

        coverage = len(query_terms & chunk_terms) / len(query_terms)
        frequency = (
            sum(
                min(query_frequencies[term], chunk_frequencies[term])
                for term in query_terms
            )
            / sum(query_frequencies.values())
        )
        phrase = (
            sum(1 for bigram in query_bigrams if bigram in chunk_bigrams)
            / len(query_bigrams)
            if query_bigrams
            else 0.0
        )
        filename_terms = set(_tokenize(chunk.filename))
        filename = (
            len(query_terms & filename_terms) / len(query_terms) if filename_terms else 0.0
        )
        joined_chunk = " ".join(chunk_tokens)
        exact_phrase = (
            1.0 if f" {query_phrase} " in f" {joined_chunk} " else 0.0
        )

        score = (
            _WEIGHT_COVERAGE * coverage
            + _WEIGHT_FREQUENCY * frequency
            + _WEIGHT_PHRASE * phrase
            + _WEIGHT_FILENAME * filename
            + _WEIGHT_EXACT_PHRASE * exact_phrase
        )
        return round(score, _SCORE_PRECISION)


# Optional test/extension seam: when set, this class is used instead of
# importing FastEmbed. Production leaves it as ``None``.
TextCrossEncoder: type | None = None


def _import_text_cross_encoder() -> type:
    """Import FastEmbed's cross-encoder class without loading a model.

    FastEmbed's dense ``TextEmbedding`` cannot rerank; reranking lives behind
    ``TextCrossEncoder`` (``fastembed.rerank.cross_encoder``). The import is
    deliberately lazy so the heuristic provider never requires the optional
    dependency. A missing/old FastEmbed is a configuration error (501), not a
    silent fallback to the heuristic reranker.
    """
    if TextCrossEncoder is not None:
        return TextCrossEncoder
    try:
        from fastembed.rerank.cross_encoder import TextCrossEncoder as imported
    except ImportError:
        try:
            # Older releases exposed the same class at the package root.
            from fastembed import TextCrossEncoder as imported  # type: ignore[attr-defined]
        except ImportError as exc:
            raise ServiceNotConfiguredError(
                "SERVICE_NOT_CONFIGURED",
                "RERANKER_PROVIDER=fastembed requires FastEmbed with cross-encoder "
                f"support (pip install 'fastembed>={FASTEMBED_MIN_VERSION}').",
            ) from exc
    except Exception as exc:  # noqa: BLE001 - broken optional dependency
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED",
            "FastEmbed could not be initialized for the neural reranker. "
            "Reinstall the optional dependency "
            f"(pip install 'fastembed>={FASTEMBED_MIN_VERSION}').",
        ) from exc
    return imported


def _is_fastembed_cross_encoder(encoder_cls: type | None) -> bool:
    """Only share the real FastEmbed model across provider instances.

    Test doubles and injected encoders are cached per provider instance so
    independent tests/tenants cannot accidentally observe one another's fake
    model state; the production model is process-wide and bounded by
    ``_MAX_CACHED_MODELS``.
    """
    if encoder_cls is None:
        return False
    module = str(getattr(encoder_cls, "__module__", ""))
    return module == "fastembed" or module.startswith("fastembed.")


def _supported_model_names(encoder_cls: type) -> set[str]:
    """Return the model names FastEmbed advertises, without downloading them."""
    lister = getattr(encoder_cls, "list_supported_models", None)
    if not callable(lister):
        return set()
    try:
        descriptions = lister()
    except Exception:  # noqa: BLE001 - the real load below reports the failure
        return set()
    names: set[str] = set()
    for description in descriptions or []:
        if isinstance(description, dict):
            name = description.get("model")
        else:
            name = getattr(description, "model", None)
        if isinstance(name, str) and name.strip():
            names.add(name.strip().casefold())
    return names


class FastEmbedReranker:
    """Local neural cross-encoder implementation of the ``Reranker`` protocol.

    The optional dependency and model are loaded lazily: constructing the
    provider only imports FastEmbed and validates the model name. The actual
    model (and any download) is created on the first :meth:`rerank` call, off
    the event loop, and cached process-wide by model name. Missing dependencies
    and unsupported models raise ``SERVICE_NOT_CONFIGURED`` (501); model load
    or inference failures raise ``SERVICE_UNAVAILABLE`` (503). There is no
    fallback to the heuristic provider.
    """

    def __init__(
        self,
        *,
        model: str = "",
        model_name: str | None = None,
        settings: Any | None = None,
        cache_dir: str | None = None,
        encoder_factory: Callable[..., Any] | None = None,
    ) -> None:
        configured = getattr(settings, "reranker_model", "") if settings else ""
        requested = model or model_name or configured or ""
        self.model_name = requested.strip() or DEFAULT_FASTEMBED_MODEL
        self.cache_dir = cache_dir
        self._encoder_factory = encoder_factory
        self._encoder_cls: type | None = None
        self._encoder: Any | None = None

        if encoder_factory is None:
            self._encoder_cls = _import_text_cross_encoder()
            self._validate_model_name(self._encoder_cls)

    @classmethod
    def from_settings(cls, settings) -> FastEmbedReranker:
        """Factory hook used by ``app.services.rag.get_reranker``."""
        return cls(settings=settings)

    @classmethod
    def clear_model_cache(cls) -> None:
        """Drop cached models (useful for tests and explicit cache reset)."""
        with _MODEL_CACHE_LOCK:
            _MODEL_CACHE.clear()

    def _validate_model_name(self, encoder_cls: type) -> None:
        supported = _supported_model_names(encoder_cls)
        if supported and self.model_name.casefold() not in supported:
            available = ", ".join(sorted(supported))
            raise ServiceNotConfiguredError(
                "SERVICE_NOT_CONFIGURED",
                f"RERANKER_MODEL '{self.model_name}' is not a supported FastEmbed "
                f"reranker model. Choose one of: {available}.",
            )

    async def rerank(
        self, *, query: str, chunks: list[RetrievedChunk], top_k: int = DEFAULT_TOP_K
    ) -> list[RetrievedChunk]:
        """Neurally score authorized candidates and return the best ``top_k``.

        The provider enforces the same hard 40-candidate bound as the retriever
        even when called directly. Scores are raw cross-encoder relevance
        values (higher is better); they are placed in ``rerank_score`` while
        ``score`` keeps the original retrieval score. Ties fall back to the
        original score, then input position, so identical inputs rank
        deterministically.
        """
        self._validate(query=query, top_k=top_k)
        candidates = list(chunks)[:MAX_CANDIDATES]
        if not candidates:
            return []

        encoder = await asyncio.to_thread(self._ensure_encoder)
        documents = [chunk.text or "" for chunk in candidates]
        try:
            raw_scores = await asyncio.to_thread(self._score, encoder, query, documents)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001 - never leak model internals
            logger.exception("Neural reranking failed for model %s", self.model_name)
            raise AppError(
                "SERVICE_UNAVAILABLE",
                "The neural reranker could not score the retrieval candidates.",
            ) from exc

        if len(raw_scores) != len(candidates):
            logger.error(
                "Neural reranker returned %d scores for %d candidates",
                len(raw_scores),
                len(candidates),
            )
            raise AppError(
                "SERVICE_UNAVAILABLE",
                "The neural reranker returned an unexpected number of scores.",
            )
        if any(not math.isfinite(score) for score in raw_scores):
            logger.error("Neural reranker returned a non-finite score")
            raise AppError(
                "SERVICE_UNAVAILABLE",
                "The neural reranker returned an invalid score.",
            )

        scored = [
            (position, chunk, score)
            for position, (chunk, score) in enumerate(zip(candidates, raw_scores, strict=True))
        ]
        scored.sort(key=lambda item: (-item[2], -item[1].score, item[0]))
        return [
            replace(chunk, rerank_score=round(score, _SCORE_PRECISION))
            for _, chunk, score in scored[:top_k]
        ]

    # ------------------------------------------------------------- validation
    @staticmethod
    def _validate(*, query: str, top_k: int) -> None:
        """Same conventions as the retriever: domain errors, not HTTP ones."""
        if not (query or "").strip():
            raise AppError("VALIDATION_ERROR", "Search query must not be empty.")
        if top_k < 1:
            raise AppError("VALIDATION_ERROR", "top_k must be at least 1.")

    # -------------------------------------------------------------- inference
    def _ensure_encoder(self) -> Any:
        """Load the cross-encoder once per model, off the event loop."""
        if self._encoder is not None:
            return self._encoder

        source = self._encoder_factory or self._encoder_cls
        if self._encoder_factory is not None or not _is_fastembed_cross_encoder(source):
            # Injected/test encoders stay private to this provider instance;
            # only the real FastEmbed class uses the bounded process-wide cache.
            self._encoder = self._build_encoder(source)
            return self._encoder

        key = (source, self.model_name, self.cache_dir)
        with _MODEL_CACHE_LOCK:
            cached = _MODEL_CACHE.get(key)
            if cached is not None:
                _MODEL_CACHE.move_to_end(key)
                self._encoder = cached
                return cached

            encoder = self._build_encoder(source)
            _MODEL_CACHE[key] = encoder
            _MODEL_CACHE.move_to_end(key)
            while len(_MODEL_CACHE) > _MAX_CACHED_MODELS:
                _MODEL_CACHE.popitem(last=False)
            self._encoder = encoder
            return encoder

    def _build_encoder(self, source: Any) -> Any:
        """Instantiate and translate failures into domain errors."""
        kwargs: dict[str, Any] = {"model_name": self.model_name}
        if self.cache_dir:
            kwargs["cache_dir"] = self.cache_dir
        try:
            return source(**kwargs)
        except ServiceNotConfiguredError:
            raise
        except ValueError as exc:
            # FastEmbed uses ValueError for unsupported model names; that is
            # configuration, while other load failures are transient.
            if "support" in str(exc).casefold():
                logger.warning(
                    "FastEmbed reranker model %s is unsupported: %s",
                    self.model_name,
                    type(exc).__name__,
                )
                raise ServiceNotConfiguredError(
                    "SERVICE_NOT_CONFIGURED",
                    f"RERANKER_MODEL '{self.model_name}' is not supported by "
                    "FastEmbed. Check the model name and the FastEmbed cache.",
                ) from exc
            logger.exception(
                "FastEmbed reranker model %s could not be loaded", self.model_name
            )
            raise AppError(
                "SERVICE_UNAVAILABLE",
                f"The neural reranker model '{self.model_name}' could not be loaded. "
                "Check RERANKER_MODEL and the FastEmbed cache.",
            ) from exc
        except Exception as exc:  # noqa: BLE001 - never leak model internals
            logger.exception(
                "FastEmbed reranker model %s could not be loaded", self.model_name
            )
            raise AppError(
                "SERVICE_UNAVAILABLE",
                f"The neural reranker model '{self.model_name}' could not be loaded. "
                "Check RERANKER_MODEL and the FastEmbed cache.",
            ) from exc

    def _score(self, encoder: Any, query: str, documents: list[str]) -> list[float]:
        """Consume FastEmbed's score generator; higher means more relevant."""
        return [float(score) for score in encoder.rerank(query, documents)]


# Compatibility aliases: the implementation is the same FastEmbed provider.
NeuralReranker = FastEmbedReranker
FastEmbedCrossEncoderReranker = FastEmbedReranker

_RERANKERS.setdefault(PROVIDER_NAME, HeuristicReranker)
_RERANKERS.setdefault(FASTEMBED_PROVIDER_NAME, FastEmbedReranker)
_RERANKERS.setdefault(NEURAL_PROVIDER_NAME, FastEmbedReranker)

__all__ = [
    "DEFAULT_FASTEMBED_MODEL",
    "DEFAULT_TOP_K",
    "FASTEMBED_MIN_VERSION",
    "FASTEMBED_PROVIDER_NAME",
    "NEURAL_PROVIDER_NAME",
    "PROVIDER_NAME",
    "FastEmbedCrossEncoderReranker",
    "FastEmbedReranker",
    "HeuristicReranker",
    "NeuralReranker",
]
