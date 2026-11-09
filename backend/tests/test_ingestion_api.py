"""End-to-end ingestion API tests: upload → extract → chunk → embed → index.

Includes the mandatory cross-tenant vector search verification at API level.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import AsyncClient

from app.core.config import Settings
from app.db.database import create_all, drop_all
from app.main import create_app
from app.services.ingestion.embeddings import HashingEmbeddingProvider
from tests.builders import minimal_pdf
from tests.conftest import (
    auth,
    create_collection,
    make_client,
    register,
)

TEST_JWT = "test-secret-key-not-for-production"


def build_settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        jwt_secret_key=TEST_JWT,
        database_url="sqlite+aiosqlite:///:memory:",
        qdrant_url=":memory:",
        max_upload_bytes=65536,
    )
    base.update(overrides)
    return Settings(**base)


@pytest_asyncio.fixture
async def app(tmp_path):
    application = create_app(build_settings(storage_dir=str(tmp_path / "uploads")))
    await create_all(application.state.engine)
    yield application
    await drop_all(application.state.engine)
    await application.state.engine.dispose()


@pytest_asyncio.fixture
async def app_no_vector_store(tmp_path):
    application = create_app(build_settings(qdrant_url="", storage_dir=str(tmp_path / "nvs")))
    await create_all(application.state.engine)
    yield application
    await drop_all(application.state.engine)
    await application.state.engine.dispose()


async def upload(
    client: AsyncClient,
    session: dict,
    *,
    collection_id: str,
    filename: str,
    content: bytes,
    content_type: str = "text/plain",
    classification: str = "internal",
):
    return await client.post(
        "/documents/upload",
        files={"file": (filename, content, content_type)},
        data={"collection_id": collection_id, "classification": classification},
        headers=auth(session),
    )


async def test_upload_indexes_document(app):
    client = make_client(app)
    async with client:
        session = await register(client, name="Ada", email="ada@example.com", org="Acme")
        collection = await create_collection(client, session, name="Handbook")

        response = await upload(
            client,
            session,
            collection_id=collection["id"],
            filename="handbook.txt",
            content=b"SecureRAG keeps every tenant isolated.\n\nEmployees must rotate keys.",
        )
        assert response.status_code == 201, response.text
        document = response.json()
        assert document["status"] == "ready"
        assert document["chunkCount"] >= 1
        assert document["pageCount"] >= 1
        assert document["fileType"] == "txt"


async def test_upload_pdf_and_docx_are_indexed(app):
    from tests.builders import minimal_docx

    client = make_client(app)
    async with client:
        session = await register(client, name="Grace", email="grace@example.com", org="Naval")
        collection = await create_collection(client, session, name="Reports")

        pdf = await upload(
            client,
            session,
            collection_id=collection["id"],
            filename="board.pdf",
            content=minimal_pdf("Quarterly revenue grew by twelve percent."),
            content_type="application/pdf",
        )
        assert pdf.status_code == 201, pdf.text
        assert pdf.json()["status"] == "ready"

        docx = await upload(
            client,
            session,
            collection_id=collection["id"],
            filename="policy.docx",
            content=minimal_docx(["Access reviews happen every ninety days."]),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        assert docx.status_code == 201, docx.text
        assert docx.json()["status"] == "ready"


async def test_unsupported_file_type_is_rejected_before_creation(app):
    client = make_client(app)
    async with client:
        session = await register(client, name="Eve", email="eve@example.com", org="Shady")
        collection = await create_collection(client, session, name="Drops")

        response = await upload(
            client,
            session,
            collection_id=collection["id"],
            filename="payload.exe",
            content=b"MZ\x90fake binary",
            content_type="application/octet-stream",
        )
        assert response.status_code == 415
        assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

        listing = await client.get("/documents", headers=auth(session))
        assert listing.status_code == 200
        assert listing.json() == []  # nothing was created


async def test_oversized_upload_is_rejected(app):
    client = make_client(app)
    async with client:
        session = await register(client, name="Bulk", email="bulk@example.com", org="Heavy")
        collection = await create_collection(client, session, name="Big")

        response = await upload(
            client,
            session,
            collection_id=collection["id"],
            filename="huge.txt",
            content=b"x" * 70000,
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


async def test_upload_into_foreign_collection_is_404(app, actor_factory):
    client_a, session_a = await actor_factory(
        name="Alice", email="alice@acme.com", org="Acme Corp"
    )
    client_b, session_b = await actor_factory(
        name="Bob", email="bob@globex.com", org="Globex Inc"
    )
    collection_a = await create_collection(client_a, session_a, name="Acme Files")

    response = await upload(
        client_b,
        session_b,
        collection_id=collection_a["id"],
        filename="intruder.txt",
        content=b"should never be accepted",
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COLLECTION_NOT_FOUND"


async def test_viewer_cannot_upload(app, actor_factory):
    owner_client, owner_session = await actor_factory(
        name="Olivia Owner", email="olivia@acme.com", org="Acme Corp"
    )
    viewer_client, viewer_session = await actor_factory(
        name="Vic Viewer",
        email="vic@acme.com",
        invited_by=(owner_client, owner_session),
        role="viewer",
    )
    collection = await create_collection(owner_client, owner_session, name="Read Only")

    response = await upload(
        viewer_client,
        viewer_session,
        collection_id=collection["id"],
        filename="notes.txt",
        content=b"viewers must not upload",
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


async def test_unreadable_file_marks_document_failed(app):
    client = make_client(app)
    async with client:
        session = await register(client, name="Fail", email="fail@example.com", org="Broken")
        collection = await create_collection(client, session, name="Ingestion")

        response = await upload(
            client,
            session,
            collection_id=collection["id"],
            filename="corrupt.pdf",
            content=b"%PDF-1.4 truncated garbage without an xref table",
            content_type="application/pdf",
        )
        assert response.status_code == 201, response.text
        document = response.json()
        assert document["status"] == "failed"  # never falsely "ready"
        assert document["chunkCount"] == 0

        fetched = await client.get(f"/documents/{document['id']}", headers=auth(session))
        assert fetched.json()["status"] == "failed"

        audit = await client.get("/audit", headers=auth(session))
        assert audit.status_code == 200
        assert any(event["action"] == "INGESTION_FAILED" for event in audit.json())


async def test_metadata_first_document_then_content(app):
    client = make_client(app)
    async with client:
        session = await register(client, name="Meta", email="meta@example.com", org="Two Phase")
        collection = await create_collection(client, session, name="Staged")

        created = await client.post(
            "/documents",
            json={
                "name": "staged.txt",
                "collection_id": collection["id"],
                "classification": "internal",
                "page_count": 0,
            },
            headers=auth(session),
        )
        assert created.status_code == 201, created.text
        assert created.json()["status"] == "processing"

        document_id = created.json()["id"]
        ingest = await client.post(
            f"/documents/{document_id}/content",
            files={"file": ("staged.txt", b"Content arrives in a second request.", "text/plain")},
            headers=auth(session),
        )
        assert ingest.status_code == 200, ingest.text
        assert ingest.json()["status"] == "ready"
        assert ingest.json()["chunkCount"] >= 1


async def test_upload_without_vector_store_marks_document_failed(app_no_vector_store):
    client = make_client(app_no_vector_store)
    async with client:
        session = await register(client, name="Neo", email="neo@example.com", org="Zion")
        collection = await create_collection(client, session, name="Offline")

        response = await upload(
            client,
            session,
            collection_id=collection["id"],
            filename="offline.txt",
            content=b"no vector backend is configured for this deployment",
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "failed"


async def test_delete_document_removes_its_vectors(app, actor_factory):
    client, session = await actor_factory(name="Dana", email="dana@example.com", org="Cleanup Co")
    collection = await create_collection(client, session, name="Temporary")
    created = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename="transient.txt",
        content=b"ephemeral knowledge that must vanish on delete",
    )
    assert created.status_code == 201
    document_id = created.json()["id"]

    deleted = await client.delete(f"/documents/{document_id}", headers=auth(session))
    assert deleted.status_code == 204

    tenant_id = session["user"]["organizationId"]
    embedder = HashingEmbeddingProvider(dimension=app.state.settings.embedding_dim)
    query = await embedder.embed_query("ephemeral knowledge")
    results = await app.state.vector_store.search(vector=query, tenant_id=tenant_id, top_k=50)
    assert all(result.document_id != document_id for result in results)


# ----------------------------------------------------- mandatory security test
async def test_cross_tenant_vector_isolation(app, actor_factory):
    """Tenant A and Tenant B upload via the API; searches must never cross."""
    client_a, session_a = await actor_factory(
        name="Alice", email="alice@acme.com", org="Acme Corp"
    )
    client_b, session_b = await actor_factory(
        name="Bob", email="bob@globex.com", org="Globex Inc"
    )
    collection_a = await create_collection(client_a, session_a, name="Acme Files")
    collection_b = await create_collection(client_b, session_b, name="Globex Files")

    created_a = await upload(
        client_a,
        session_a,
        collection_id=collection_a["id"],
        filename="acme.txt",
        content=b"Acme secret merger documents are stored safely.",
    )
    created_b = await upload(
        client_b,
        session_b,
        collection_id=collection_b["id"],
        filename="globex.txt",
        content=b"Globex rocket shipping specs are stored safely.",
    )
    assert created_a.status_code == 201 and created_b.status_code == 201
    document_a = created_a.json()["id"]
    document_b = created_b.json()["id"]
    assert created_a.json()["status"] == "ready"
    assert created_b.json()["status"] == "ready"

    tenant_a = session_a["user"]["organizationId"]
    tenant_b = session_b["user"]["organizationId"]
    embedder = HashingEmbeddingProvider(dimension=app.state.settings.embedding_dim)
    store = app.state.vector_store
    query = await embedder.embed_query("secret documents stored safely")

    results_a = await store.search(vector=query, tenant_id=tenant_a, top_k=50)
    assert {result.document_id for result in results_a} == {document_a}
    assert document_b not in {result.document_id for result in results_a}

    results_b = await store.search(vector=query, tenant_id=tenant_b, top_k=50)
    assert {result.document_id for result in results_b} == {document_b}
    assert document_a not in {result.document_id for result in results_b}

    # a foreign tenant id supplied by a caller must never widen the search
    sneaky = await store.search(
        vector=query,
        tenant_id=tenant_a,
        top_k=50,
        extra_filter={"tenant_id": tenant_b},
    )
    assert {result.document_id for result in sneaky} == {document_a}
