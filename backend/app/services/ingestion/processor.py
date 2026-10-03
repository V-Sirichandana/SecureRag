"""File → normalized text segments (one segment per page when available).

Supported formats: PDF, DOCX and plain-text variants (txt, md, csv, ...).
The processor never sees tenant information — identity metadata comes from the
authenticated caller in the pipeline, never from the file itself.
"""

from __future__ import annotations

import io
import re

from app.core.exceptions import AppError
from app.services.rag.base import ProcessedChunk

# extension → handler
PLAIN_TEXT_EXTENSIONS = {"txt", "md", "markdown", "csv", "tsv", "log", "json", "yaml", "yml"}
SUPPORTED_EXTENSIONS = PLAIN_TEXT_EXTENSIONS | {"pdf", "docx"}

_TEXT_LIKE_CONTENT_TYPES = ("text/", "application/json", "application/xml")


def normalize_file_name(file_name: str) -> str:
    """Strip any path components a client may have sent."""
    return re.sub(r"[^\w.\- ]+", "_", (file_name or "").replace("\\", "/").split("/")[-1])[
        :400
    ] or "upload"


def file_extension(file_name: str) -> str:
    name = normalize_file_name(file_name)
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def is_supported(file_name: str, content_type: str | None = None) -> bool:
    extension = file_extension(file_name)
    if extension in SUPPORTED_EXTENSIONS:
        return True
    if extension:
        return False
    # no extension at all: only accept when the browser says it is text
    return not content_type or content_type.startswith(_TEXT_LIKE_CONTENT_TYPES)


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1")


class FileDocumentProcessor:
    """Implements :class:`DocumentProcessor` for the formats above."""

    async def process(
        self, *, document_id: str, file_name: str, content: bytes
    ) -> list[ProcessedChunk]:
        if not content:
            raise AppError("EMPTY_DOCUMENT", "The uploaded file is empty.")

        extension = file_extension(file_name)
        base_metadata = {"document_id": document_id, "filename": normalize_file_name(file_name)}

        if extension == "pdf":
            pages = await self._pdf_pages(content)
        elif extension == "docx":
            pages = await self._docx_pages(content)
        elif extension in PLAIN_TEXT_EXTENSIONS or not extension:
            pages = self._text_pages(content)
        else:
            raise AppError(
                "UNSUPPORTED_FILE_TYPE",
                f"Files of type '{extension}' are not supported. "
                "Supported formats: PDF, DOCX, TXT, MD, CSV, JSON.",
            )

        segments: list[ProcessedChunk] = []
        for page_number, text in pages:
            normalized = _normalize(text)
            if not normalized:
                continue
            segments.append(
                ProcessedChunk(
                    text=normalized,
                    metadata={**base_metadata, "page": page_number},
                )
            )
        if not segments:
            raise AppError(
                "EMPTY_DOCUMENT",
                "No extractable text was found in the uploaded file.",
            )
        return segments

    # ------------------------------------------------------------------ plain
    def _text_pages(self, content: bytes) -> list[tuple[int, str]]:
        # form-feed is the classic page separator for text exports
        pages = _decode(content).split("\f")
        return [(index + 1, page) for index, page in enumerate(pages)]

    # -------------------------------------------------------------------- pdf
    async def _pdf_pages(self, content: bytes) -> list[tuple[int, str]]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise AppError(
                "SERVICE_NOT_CONFIGURED", "PDF support requires the 'pypdf' package."
            ) from exc
        try:
            reader = PdfReader(io.BytesIO(content))
            return [
                (index + 1, page.extract_text() or "")
                for index, page in enumerate(reader.pages)
            ]
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                "DOCUMENT_UNREADABLE",
                "The PDF could not be read. It may be corrupted or password protected.",
            ) from exc

    # ------------------------------------------------------------------- docx
    async def _docx_pages(self, content: bytes) -> list[tuple[int, str]]:
        try:
            import docx  # python-docx
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise AppError(
                "SERVICE_NOT_CONFIGURED", "DOCX support requires the 'python-docx' package."
            ) from exc
        try:
            document = docx.Document(io.BytesIO(content))
        except Exception as exc:
            raise AppError(
                "DOCUMENT_UNREADABLE",
                "The DOCX file could not be read. It may be corrupted.",
            ) from exc
        paragraphs = [paragraph.text for paragraph in document.paragraphs]
        return [(1, "\n\n".join(paragraphs))]


__all__ = [
    "FileDocumentProcessor",
    "SUPPORTED_EXTENSIONS",
    "file_extension",
    "is_supported",
    "normalize_file_name",
]
