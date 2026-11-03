"""Vector store: indexing, retrieval, deletion and MANDATORY tenant isolation.

Two tenants share one Qdrant collection; isolation comes from the server-side
tenant filter — never from collection naming, and never from client input.
"""

from __future__ import annotations

import uuid

import pytest

from app.services.ingestion.embeddings import HashingEmbeddingProvider
from app.services.ingestion.vector_store import (
    QdrantVectorStore,
    VectorDimensionMismatchError,
    build_tenant_filter,
)

DIMENSION = 32


@pytest.fixture
def store() -> QdrantVectorStore:
    return QdrantVectorStore(url=":memory:", collection="test_chunks")


@pytest.fixture
def embedder() -> HashingEmbeddingProvider:
    return HashingEmbeddingProvider(dimension=DIMENSION)


def payload(
    *,
    tenant_id: str,
    document_id: str,
    chunk_id: str | None = None,
    text: str,
    collection_id: str | None = None,
    page: int = 1,
) -> dict:
    return {
        "chunk_id": chunk_id or str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "document_id": document_id,
        "collection_id": collection_id,
        "page": page,
        "filename": "file.txt",
        "text": text,
    }


async def index(store: QdrantVectorStore, embedder, tenant_id: str, document_id: str, texts):
    vectors = await embedder.embed_documents(texts)
    payloads = [
        payload(tenant_id=tenant_id, document_id=document_id, text=text) for text in texts
    ]
    await store.upsert_chunks(vectors=vectors, payloads=payloads, vector_size=DIMENSION)
    return payloads


async def test_upsert_then_search_returns_own_chunks(store, embedder):
    await index(store, embedder, "tenant-a", "doc-a", ["acme secret roadmap"])
    query = await embedder.embed_query("acme secret roadmap")
    results = await store.search(vector=query, tenant_id="tenant-a", top_k=5)
    assert results
    assert results[0].document_id == "doc-a"
    assert "acme secret roadmap" in results[0].text
    assert results[0].page_number == 1


async def test_search_before_anything_indexed_is_empty(store, embedder):
    query = await embedder.embed_query("anything at all")
    assert await store.search(vector=query, tenant_id="tenant-a") == []


async def test_search_can_filter_by_collection_id(store, embedder):
    vectors = await embedder.embed_documents(["alpha collection text", "beta collection text"])
    await store.upsert_chunks(
        vectors=vectors,
        payloads=[
            payload(
                tenant_id="tenant-a", document_id="doc-a", text="alpha collection text",
                collection_id="col-a",
            ),
            payload(
                tenant_id="tenant-a", document_id="doc-b", text="beta collection text",
                collection_id="col-b",
            ),
        ],
        vector_size=DIMENSION,
    )

    query = await embedder.embed_query("collection text")
    unfiltered = await store.search(vector=query, tenant_id="tenant-a", top_k=10)
    assert {result.document_id for result in unfiltered} == {"doc-a", "doc-b"}

    filtered = await store.search(
        vector=query, tenant_id="tenant-a", collection_id="col-a", top_k=10
    )
    assert {result.document_id for result in filtered} == {"doc-a"}
    assert all(result.collection_id == "col-a" for result in filtered)


async def test_delete_document_removes_only_that_documents_vectors(store, embedder):
    await index(store, embedder, "tenant-a", "doc-a", ["first document text"])
    await index(store, embedder, "tenant-a", "doc-b", ["second document text"])

    await store.delete_document(tenant_id="tenant-a", document_id="doc-a")

    query = await embedder.embed_query("document text")
    remaining = await store.search(vector=query, tenant_id="tenant-a", top_k=10)
    assert [result.document_id for result in remaining] == ["doc-b"]


async def test_delete_document_for_unknown_document_is_a_noop(store, embedder):
    await store.delete_document(tenant_id="tenant-a", document_id="missing")


async def test_mismatched_vectors_and_payloads_rejected(store):
    with pytest.raises(ValueError):
        await store.upsert_chunks(
            vectors=[[0.0] * DIMENSION], payloads=[], vector_size=DIMENSION
        )


async def test_existing_collection_dimension_mismatch_is_rejected_without_changes(
    store, embedder
):
    """A wrong EMBEDDING_DIM must fail closed, never recreate the collection."""
    await index(store, embedder, "tenant-a", "doc-a", ["original retained text"])

    with pytest.raises(VectorDimensionMismatchError) as excinfo:
        await store.upsert_chunks(
            vectors=[[0.0] * 16],
            payloads=[
                payload(
                    tenant_id="tenant-a",
                    document_id="doc-b",
                    text="must never be written",
                )
            ],
            vector_size=16,
        )
    assert excinfo.value.status_code == 503

    info = store._client.get_collection("test_chunks")
    assert info.config.params.vectors.size == DIMENSION
    assert store._client.count(collection_name="test_chunks", exact=True).count == 1

    query = await embedder.embed_query("original retained text")
    results = await store.search(vector=query, tenant_id="tenant-a", top_k=5)
    assert [result.document_id for result in results] == ["doc-a"]


# --------------------------------------------------------------------- security
async def test_tenant_isolation_search_never_crosses_tenants(store, embedder):
    """MANDATORY: Tenant A sees only A's chunks, Tenant B only B's."""
    docs_a = ["acme merger plan", "acme secret recipe"]
    docs_b = ["globex shipping logistics", "globex starship specs"]
    await index(store, embedder, "tenant-a", "doc-a1", [docs_a[0]])
    await index(store, embedder, "tenant-a", "doc-a2", [docs_a[1]])
    await index(store, embedder, "tenant-b", "doc-b1", [docs_b[0]])
    await index(store, embedder, "tenant-b", "doc-b2", [docs_b[1]])

    query_a = await embedder.embed_query("secret plan document")
    results_a = await store.search(vector=query_a, tenant_id="tenant-a", top_k=10)
    assert results_a, "tenant A must retrieve its own chunks"
    ids_a = {result.document_id for result in results_a}
    assert ids_a == {"doc-a1", "doc-a2"}
    assert ids_a.isdisjoint({"doc-b1", "doc-b2"})

    query_b = await embedder.embed_query("secret plan document")
    results_b = await store.search(vector=query_b, tenant_id="tenant-b", top_k=10)
    assert results_b, "tenant B must retrieve its own chunks"
    ids_b = {result.document_id for result in results_b}
    assert ids_b == {"doc-b1", "doc-b2"}
    assert ids_b.isdisjoint({"doc-a1", "doc-a2"})


async def test_foreign_tenant_id_cannot_bypass_the_filter(store, embedder):
    """A caller-supplied tenant_id in extra_filter must be ignored."""
    await index(store, embedder, "tenant-a", "doc-a", ["private a material"])
    await index(store, embedder, "tenant-b", "doc-b", ["private b material"])

    query = await embedder.embed_query("private material")
    # attacker authenticated as tenant-a tries to search as tenant-b
    results = await store.search(
        vector=query,
        tenant_id="tenant-a",
        top_k=10,
        extra_filter={"tenant_id": "tenant-b"},
    )
    assert results, "tenant A still gets its own results"
    assert {result.document_id for result in results} == {"doc-a"}
    assert all(result.document_id != "doc-b" for result in results)


def test_build_tenant_filter_ignores_caller_tenant():
    query_filter = build_tenant_filter("tenant-a", extra_filter={"tenant_id": "tenant-b"})
    tenant_conditions = [
        condition
        for condition in query_filter.must
        if getattr(condition, "key", None) == "tenant_id"
    ]
    assert len(tenant_conditions) == 1
    assert tenant_conditions[0].match.value == "tenant-a"


def test_build_tenant_filter_supports_extra_constraints():
    query_filter = build_tenant_filter(
        "tenant-a", collection_id="col-1", extra_filter={"classification": "confidential"}
    )
    keys = [getattr(condition, "key", None) for condition in query_filter.must]
    assert keys == ["tenant_id", "collection_id", "classification"]
