"""Deterministic offline lexical reranker (``heuristic`` provider).

Re-scores already-authorized retrieval candidates by lexical overlap between
the query and each chunk: distinct-term coverage, term-frequency overlap,
contiguous query-bigram coverage, filename overlap and an exact-phrase bonus.
Standard library only — no model, no network, no API key — so development and
tests stay offline and identical inputs always produce identical output.

This is NOT a neural cross-encoder and makes no claim of semantic
understanding. It is the transparent baseline behind the
:class:`~app.services.rag.base.Reranker` protocol, and the original vector
retrieval score is never overwritten: both scores are kept
(``score`` = vector similarity, ``rerank_score`` = lexical relevance).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace
from unicodedata import normalize as unicodedata_normalize

from app.core.exceptions import AppError
from app.services.rag import _RERANKERS
from app.services.rag.base import RetrievedChunk

PROVIDER_NAME = "heuristic"
DEFAULT_TOP_K = 5

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


_RERANKERS.setdefault(PROVIDER_NAME, HeuristicReranker)

__all__ = ["DEFAULT_TOP_K", "PROVIDER_NAME", "HeuristicReranker"]
