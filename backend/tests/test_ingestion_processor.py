"""Document processing: TXT / PDF / DOCX extraction and validation."""

from __future__ import annotations

import pytest

from app.core.exceptions import AppError
from app.services.ingestion.processor import FileDocumentProcessor, file_extension, is_supported
from tests.builders import minimal_docx, minimal_pdf


@pytest.fixture
def processor() -> FileDocumentProcessor:
    return FileDocumentProcessor()


async def test_txt_extraction_normalizes_and_tags_metadata(processor):
    content = b"Hello   SecureRAG.\r\n\r\n\r\n\r\nSecond   paragraph."
    segments = await processor.process(
        document_id="doc-1", file_name="notes.txt", content=content
    )
    assert len(segments) == 1
    segment = segments[0]
    assert segment.text == "Hello SecureRAG.\n\nSecond paragraph."
    assert segment.metadata == {
        "document_id": "doc-1",
        "filename": "notes.txt",
        "page": 1,
    }


async def test_txt_form_feed_creates_pages(processor):
    segments = await processor.process(
        document_id="doc-2", file_name="export.txt", content=b"page one\fpage two"
    )
    assert [segment.metadata["page"] for segment in segments] == [1, 2]
    assert segments[0].text == "page one"
    assert segments[1].text == "page two"


async def test_pdf_extraction(processor):
    content = minimal_pdf("Confidential quarterly numbers for the board")
    segments = await processor.process(
        document_id="doc-3", file_name="report.pdf", content=content
    )
    assert len(segments) == 1
    assert "Confidential quarterly numbers" in segments[0].text
    assert segments[0].metadata["page"] == 1
    assert segments[0].metadata["filename"] == "report.pdf"


async def test_docx_extraction(processor):
    content = minimal_docx(
        ["Employees must rotate access keys quarterly.", "Escalate incidents within 24 hours."]
    )
    segments = await processor.process(
        document_id="doc-4", file_name="policy.docx", content=content
    )
    assert len(segments) == 1
    assert "rotate access keys" in segments[0].text
    assert "24 hours" in segments[0].text


async def test_unsupported_extension_is_rejected(processor):
    with pytest.raises(AppError) as excinfo:
        await processor.process(document_id="doc-5", file_name="malware.exe", content=b"MZ")
    assert excinfo.value.code == "UNSUPPORTED_FILE_TYPE"
    assert excinfo.value.status_code == 415


async def test_empty_file_is_rejected(processor):
    with pytest.raises(AppError) as excinfo:
        await processor.process(document_id="doc-6", file_name="empty.txt", content=b"")
    assert excinfo.value.code == "EMPTY_DOCUMENT"
    assert excinfo.value.status_code == 422


async def test_pdf_without_extractable_text_is_rejected(processor):
    with pytest.raises(AppError) as excinfo:
        await processor.process(document_id="doc-7", file_name="blank.pdf", content=minimal_pdf(""))
    assert excinfo.value.code == "EMPTY_DOCUMENT"


async def test_unreadable_pdf_reports_document_unreadable(processor):
    with pytest.raises(AppError) as excinfo:
        await processor.process(
            document_id="doc-8", file_name="broken.pdf", content=b"%PDF-1.4 truncated garbage"
        )
    assert excinfo.value.code == "DOCUMENT_UNREADABLE"
    assert excinfo.value.status_code == 422


def test_file_extension_and_support_matrix():
    assert file_extension("Report.FINAL.PDF") == "pdf"
    assert file_extension("README") == ""
    assert file_extension("../../etc/passwd") == ""  # path components stripped
    assert is_supported("handbook.pdf")
    assert is_supported("notes.txt")
    assert is_supported("README", "text/plain")
    assert not is_supported("setup.exe")
    assert not is_supported("README", "application/pdf")
