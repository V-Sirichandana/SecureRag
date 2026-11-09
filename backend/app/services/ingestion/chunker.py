"""Deterministic, boundary-aware chunking.

Configuration (CHUNK_SIZE / CHUNK_OVERLAP) comes from application settings —
never hard-coded at call sites. Guarantees:

* deterministic output — same input always yields the same chunk ids
* no empty chunks, every chunk within ``chunk_size``
* paragraph/sentence boundaries preferred over mid-word cuts
* ``overlap`` characters of shared context between consecutive chunks
* page and document metadata carried through to every chunk
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.services.rag.base import ProcessedChunk

CHUNK_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "securerag:chunk:v1")

_PARAGRAPH_SEP = "\n\n"
_SENTENCE_ENDINGS = (".", "!", "?", "。", "！", "？")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    page: int
    index: int
    metadata: dict[str, Any] = field(default_factory=dict)


def stable_chunk_id(*, document_id: str, page: int, index: int, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return str(uuid.uuid5(CHUNK_ID_NAMESPACE, f"{document_id}:{page}:{index}:{digest}"))


def normalize_whitespace(text: str) -> str:
    """Collapse excessive whitespace while keeping paragraph structure."""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    normalized = "\n".join(lines)
    while _PARAGRAPH_SEP * 2 in normalized:
        normalized = normalized.replace(_PARAGRAPH_SEP * 2, _PARAGRAPH_SEP)
    return normalized.strip()


class ChunkingService:
    def __init__(self, *, chunk_size: int, overlap: int) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap must be >= 0 and < chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    # ------------------------------------------------------------- public API
    def chunk(self, segments: list[ProcessedChunk]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for segment in segments:
            text = normalize_whitespace(segment.text)
            if not text:
                continue
            page = int(segment.metadata.get("page", 1))
            for piece in self._split(text):
                index = len(chunks)
                chunks.append(
                    Chunk(
                        chunk_id=stable_chunk_id(
                            document_id=str(segment.metadata.get("document_id", "")),
                            page=page,
                            index=index,
                            text=piece,
                        ),
                        text=piece,
                        page=page,
                        index=index,
                        metadata=dict(segment.metadata),
                    )
                )
        return chunks

    # -------------------------------------------------------------- internals
    def _split(self, text: str) -> list[str]:
        pieces: list[str] = []
        start = 0
        length = len(text)
        while start < length:
            hard_end = min(start + self.chunk_size, length)
            end = hard_end if hard_end >= length else self._best_boundary(text, start, hard_end)
            piece = text[start:end].strip()
            if piece:
                pieces.append(piece)
            if hard_end >= length:
                break
            next_start = max(end - self.overlap, start + 1)
            next_start = self._snap_forward(text, next_start, limit=end)
            start = next_start
        return pieces

    def _best_boundary(self, text: str, start: int, hard_end: int) -> int:
        """Latest comfortable split point inside [start + size/2, hard_end]."""
        floor = start + (self.chunk_size // 2)
        window = text[floor:hard_end]
        for separator in (_PARAGRAPH_SEP, "\n"):
            position = window.rfind(separator)
            if position != -1:
                return floor + position + len(separator)
        for ending in _SENTENCE_ENDINGS:
            position = window.rfind(ending)
            if position != -1 and position + 1 < len(window):
                return floor + position + 1
        position = window.rfind(" ")
        if position != -1:
            return floor + position
        return hard_end

    def _snap_forward(self, text: str, position: int, *, limit: int) -> int:
        """Move to the next whitespace so chunks never start mid-word."""
        index = position
        while index < limit and index < len(text) and not text[index].isspace():
            index += 1
        while index < limit and index < len(text) and text[index].isspace():
            index += 1
        return min(max(index, position), limit)


__all__ = ["Chunk", "ChunkingService", "normalize_whitespace", "stable_chunk_id"]
