"""Chunking: determinism, overlap, boundaries, metadata, no empty chunks."""

from __future__ import annotations

import pytest

from app.services.ingestion.chunker import (
    ChunkingService,
    normalize_whitespace,
    stable_chunk_id,
)
from app.services.rag.base import ProcessedChunk
from tests.builders import word_blob


def segments(text: str, *, document_id: str = "doc-1", page: int = 1) -> list[ProcessedChunk]:
    return [
        ProcessedChunk(
            text=text,
            metadata={"document_id": document_id, "filename": f"{document_id}.txt", "page": page},
        )
    ]


def test_chunks_are_deterministic():
    service = ChunkingService(chunk_size=120, overlap=30)
    text = word_blob(200)
    first = service.chunk(segments(text))
    second = service.chunk(segments(text))
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert [chunk.text for chunk in first] == [chunk.text for chunk in second]
    assert len(first) > 1


def test_no_empty_chunks_and_size_bound():
    service = ChunkingService(chunk_size=100, overlap=25)
    normalized = normalize_whitespace(word_blob(300))
    chunks = service.chunk(segments(normalized))
    assert chunks
    for chunk in chunks:
        assert chunk.text.strip()
        assert len(chunk.text) <= 100
        assert chunk.text in normalized  # pieces are exact slices of the source


def test_overlap_shares_context_between_consecutive_chunks():
    service = ChunkingService(chunk_size=90, overlap=30)
    chunks = service.chunk(segments(word_blob(200)))
    assert len(chunks) > 2
    for previous, following in zip(chunks, chunks[1:], strict=False):
        # the first characters of the next chunk must come from the previous one
        assert following.text[:10] in previous.text


def test_paragraph_boundaries_are_preferred():
    service = ChunkingService(chunk_size=120, overlap=20)
    text = "\n\n".join(f"Sentence number {index} ends here." for index in range(20))
    chunks = service.chunk(segments(text))
    assert len(chunks) > 1
    for chunk in chunks[:-1]:
        assert chunk.text.endswith(".")  # cut at a paragraph, never mid-word


def test_metadata_and_pages_are_preserved():
    service = ChunkingService(chunk_size=80, overlap=20)
    multi = [
        ProcessedChunk(
            text=word_blob(60, prefix="alpha"),
            metadata={"document_id": "doc-9", "filename": "multi.txt", "page": 1},
        ),
        ProcessedChunk(
            text=word_blob(60, prefix="beta"),
            metadata={"document_id": "doc-9", "filename": "multi.txt", "page": 2},
        ),
    ]
    chunks = service.chunk(multi)
    assert {chunk.page for chunk in chunks} == {1, 2}
    assert all(chunk.metadata["document_id"] == "doc-9" for chunk in chunks)
    assert all(chunk.metadata["filename"] == "multi.txt" for chunk in chunks)
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


def test_chunk_ids_stable_but_document_scoped():
    text = word_blob(40)
    a = stable_chunk_id(document_id="doc-a", page=1, index=0, text=text)
    a_again = stable_chunk_id(document_id="doc-a", page=1, index=0, text=text)
    b = stable_chunk_id(document_id="doc-b", page=1, index=0, text=text)
    assert a == a_again
    assert a != b


def test_whitespace_is_normalized():
    service = ChunkingService(chunk_size=200, overlap=40)
    messy = "too    many\tspaces   here\n\n\n\nand blank lines"
    chunks = service.chunk(segments(messy))
    assert chunks
    for chunk in chunks:
        assert "  " not in chunk.text
        assert "\t" not in chunk.text


def test_empty_segments_produce_no_chunks():
    service = ChunkingService(chunk_size=100, overlap=10)
    assert service.chunk(segments("   \n\n  ")) == []


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError):
        ChunkingService(chunk_size=100, overlap=100)
    with pytest.raises(ValueError):
        ChunkingService(chunk_size=100, overlap=-1)
    with pytest.raises(ValueError):
        ChunkingService(chunk_size=0, overlap=0)
