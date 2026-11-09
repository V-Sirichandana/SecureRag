"""Non-destructive embedding migration planning and tooling tests.

These tests never reindex production data and never shrink/delete the active
collection. They use the normal in-memory test app, plus fake collection
metadata and fake target stores, to verify planning, tenant scoping, progress
journaling and validation gates.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest
from sqlalchemy import func, select

from app.models import DocumentChunk
from app.services.ingestion.embedding_migration import (
    CollectionInfo,
    EmbeddingProfile,
    MigrationProgress,
    MigrationProgressStore,
    build_embedding_migration_plan,
    build_target_collection_name,
    reembed_document,
    validate_embedding_migration,
)
from app.services.ingestion.embeddings import HashingEmbeddingProvider
from tests.conftest import create_collection
from tests.test_retrieval import upload

SOURCE_PROFILE = EmbeddingProfile("hashing", "hashing-v1", 384)
TARGET_PROFILE = EmbeddingProfile("fastembed", "BAAI/bge-small-en-v1.5", 384)


@dataclass
class FakeCatalog:
    entries: dict[str, CollectionInfo] = field(default_factory=dict)
    calls: list[tuple[str, str | None]] = field(default_factory=list)

    def inspect(
        self, name: str, *, tenant_id: str | None = None
    ) -> CollectionInfo | None:
        self.calls.append((name, tenant_id))
        return self.entries.get(name)


async def index_document(app, actor_factory, *, name: str, email: str, org: str, text: str):
    client, session = await actor_factory(name=name, email=email, org=org)
    collection = await create_collection(client, session, name=f"{name} files")
    document = await upload(
        client,
        session,
        collection_id=collection["id"],
        filename=f"{name.lower()}.txt",
        content=text.encode("utf-8"),
    )
    return client, session, document


async def make_plan(
    app,
    *,
    tenant_id: str | None = None,
    source_profile: EmbeddingProfile = SOURCE_PROFILE,
    target_profile: EmbeddingProfile = TARGET_PROFILE,
    source_info: CollectionInfo | None = None,
    target_info: CollectionInfo | None = None,
    target_collection: str | None = None,
):
    target_name = (
        target_collection
        or build_target_collection_name(app.state.settings.qdrant_collection, target_profile)
    )
    entries: dict[str, CollectionInfo] = {}
    if source_info is not None:
        entries[app.state.settings.qdrant_collection] = source_info
    if target_info is not None:
        entries[target_name] = CollectionInfo(
            target_name, target_info.dimension, target_info.point_count
        )
    catalog = FakeCatalog(entries)
    async with app.state.session_factory() as db:
        plan = await build_embedding_migration_plan(
            db=db,
            settings=app.state.settings,
            source_profile=source_profile,
            target_profile=target_profile,
            tenant_id=tenant_id,
            target_collection=target_name,
            catalog=catalog,
        )
    return plan, catalog, target_name


def test_target_collection_name_is_separate_and_dimension_specific():
    first = build_target_collection_name("securerag", TARGET_PROFILE)
    second = build_target_collection_name("securerag", TARGET_PROFILE)
    other_dimension = build_target_collection_name(
        "securerag", EmbeddingProfile("fastembed", "other/model", 768)
    )

    assert first == second
    assert first != "securerag"
    assert first.startswith("securerag__fastembed__")
    assert "__384__" in first
    assert other_dimension != first
    assert "__768__" in other_dimension


async def test_plan_is_read_only_and_targeted_at_a_new_collection(app, actor_factory):
    _client, session, document = await index_document(
        app,
        actor_factory,
        name="Ada",
        email="ada@acme-migration.io",
        org="Acme Migration",
        text="semantic migration source content for the target collection",
    )
    plan, catalog, target_name = await make_plan(
        app,
        tenant_id=session["user"]["organizationId"],
        source_info=CollectionInfo("securerag", 384, 1),
    )

    assert plan.can_start, plan.errors
    assert plan.source_collection == "securerag"
    assert plan.target_collection == target_name != plan.source_collection
    assert plan.source_profile == SOURCE_PROFILE
    assert plan.target_profile == TARGET_PROFILE
    assert plan.target_info is None
    assert plan.total_documents == 1
    assert plan.total_chunks >= 1
    assert plan.documents[0].document_id == document["id"]
    assert any("does not exist yet" in warning for warning in plan.warnings)
    # Only read-only metadata calls happened; no collection was created/mutated.
    assert catalog.calls


async def test_target_dimension_mismatch_is_rejected(app):
    plan, _catalog, target_name = await make_plan(
        app,
        source_info=CollectionInfo("securerag", 384, 0),
        target_info=CollectionInfo("securerag", 768, 0),
    )

    assert not plan.can_start
    assert any("dimension" in error for error in plan.errors)
    assert plan.target_collection == target_name


async def test_source_dimension_mismatch_is_rejected(app):
    plan, _catalog, _target_name = await make_plan(
        app,
        source_info=CollectionInfo("securerag", 768, 0),
    )

    assert not plan.can_start
    assert any("Source collection" in error and "dimension" in error for error in plan.errors)


async def test_same_collection_is_rejected(app):
    plan, _catalog, _target_name = await make_plan(
        app,
        target_collection="securerag",
        source_info=CollectionInfo("securerag", 384, 0),
    )

    assert not plan.can_start
    assert any("different from source_collection" in error for error in plan.errors)


async def test_plan_scopes_documents_to_one_tenant(app, actor_factory):
    _client_a, session_a, document_a = await index_document(
        app,
        actor_factory,
        name="Alice",
        email="alice@tenant-a.io",
        org="Tenant A",
        text="tenant a migration content about quarterly planning",
    )
    _client_b, session_b, document_b = await index_document(
        app,
        actor_factory,
        name="Bob",
        email="bob@tenant-b.io",
        org="Tenant B",
        text="tenant b migration content about unrelated logistics",
    )

    plan_a, _catalog, _target = await make_plan(
        app,
        tenant_id=session_a["user"]["organizationId"],
        source_info=CollectionInfo("securerag", 384, 2),
    )
    assert {document.document_id for document in plan_a.documents} == {document_a["id"]}
    assert all(
        document.tenant_id == session_a["user"]["organizationId"]
        for document in plan_a.documents
    )
    assert document_b["id"] not in {document.document_id for document in plan_a.documents}

    plan_all, _catalog, _target = await make_plan(
        app,
        source_info=CollectionInfo("securerag", 384, 2),
    )
    assert {document.document_id for document in plan_all.documents} == {
        document_a["id"],
        document_b["id"],
    }


async def test_progress_tracks_failures_and_blocks_cutover(app, actor_factory, tmp_path):
    _client, session, document = await index_document(
        app,
        actor_factory,
        name="Mia",
        email="mia@progress-co.io",
        org="Progress Co",
        text="progress tracked migration content for one document",
    )
    plan, _catalog, _target = await make_plan(
        app,
        tenant_id=session["user"]["organizationId"],
        source_info=CollectionInfo("securerag", 384, 1),
    )
    item = plan.documents[0]
    progress = MigrationProgress.from_plan(plan)

    progress.record_failure(item, "simulated embedding failure")
    assert progress.failed_documents == 1
    assert progress.status == "completed"
    assert not progress.ready_for_cutover
    with pytest.raises(ValueError):
        progress.mark_validated(ok=True)

    store = MigrationProgressStore(tmp_path)
    store.save(progress)
    loaded = store.load(plan.plan_id)
    assert loaded is not None
    assert loaded.failures[0].document_id == document["id"]
    assert loaded.failures[0].error == "simulated embedding failure"

    success = MigrationProgress.from_plan(plan)
    success.record_success(item)
    success.mark_validated(ok=True)
    assert success.ready_for_cutover


async def test_validation_requires_exact_dimension_and_point_count(app, actor_factory):
    _client, session, _document = await index_document(
        app,
        actor_factory,
        name="Val",
        email="val@validation-co.io",
        org="Validation Co",
        text="validation needs an exact target dimension and point count",
    )
    plan, _catalog, target_name = await make_plan(
        app,
        tenant_id=session["user"]["organizationId"],
        source_info=CollectionInfo("securerag", 384, 1),
    )
    progress = MigrationProgress.from_plan(plan)
    for item in plan.documents:
        progress.record_success(item)

    good = await validate_embedding_migration(
        plan,
        catalog=FakeCatalog(
            {target_name: CollectionInfo(target_name, 384, plan.total_chunks)}
        ),
        progress=progress,
    )
    assert good.ok, good.errors

    wrong_count = await validate_embedding_migration(
        plan,
        catalog=FakeCatalog(
            {target_name: CollectionInfo(target_name, 384, plan.total_chunks + 1)}
        ),
        progress=progress,
    )
    assert not wrong_count.ok
    assert any("expected" in error for error in wrong_count.errors)

    wrong_dimension = await validate_embedding_migration(
        plan,
        catalog=FakeCatalog(
            {target_name: CollectionInfo(target_name, 768, plan.total_chunks)}
        ),
        progress=progress,
    )
    assert not wrong_dimension.ok
    assert any("dimension" in error for error in wrong_dimension.errors)

    progress.mark_validated(ok=good.ok)
    assert progress.ready_for_cutover


class RecordingTargetStore:
    """Target-only fake: any source-style delete would fail the test."""

    def __init__(self, collection_name: str) -> None:
        self.collection_name = collection_name
        self.upserts: list[tuple[list[list[float]], list[dict]]] = []

    async def upsert_chunks(self, *, vectors, payloads, vector_size):
        assert vector_size == 384
        self.upserts.append((vectors, payloads))

    async def delete_document(self, *, tenant_id, document_id):
        raise AssertionError("migration must not delete source vectors")

    async def search(self, **_kwargs):
        return []


class FakeTargetEmbedder:
    provider_name = "fastembed"
    model_name = TARGET_PROFILE.model
    dimension = TARGET_PROFILE.dimension

    def __init__(self) -> None:
        self.documents: list[list[str]] = []

    async def embed_documents(self, texts):
        self.documents.append(list(texts))
        return [[0.1] * self.dimension for _ in texts]

    async def embed_query(self, text):
        return [0.1] * self.dimension


async def test_reembed_writes_only_to_target_and_preserves_tenant_payload(
    app, actor_factory, tmp_path
):
    _client, session, document = await index_document(
        app,
        actor_factory,
        name="Rae",
        email="rae@executor-co.io",
        org="Executor Co",
        text="reembedding copies stored chunks into a separate target collection",
    )
    plan, _catalog, target_name = await make_plan(
        app,
        tenant_id=session["user"]["organizationId"],
        source_info=CollectionInfo("securerag", 384, 1),
        target_info=CollectionInfo(
            build_target_collection_name("securerag", TARGET_PROFILE), 384, 0
        ),
    )
    target = RecordingTargetStore(target_name)
    embedder = FakeTargetEmbedder()
    progress = MigrationProgress.from_plan(plan)
    store = MigrationProgressStore(tmp_path)

    async with app.state.session_factory() as db:
        ok = await reembed_document(
            db=db,
            plan=plan,
            document=plan.documents[0],
            embedder=embedder,
            target_store=target,
            progress=progress,
            progress_store=store,
        )

    assert ok
    assert progress.completed_documents == 1
    assert progress.completed_chunks == plan.total_chunks
    assert len(target.upserts) == 1
    vectors, payloads = target.upserts[0]
    assert len(vectors) == len(payloads) == plan.total_chunks
    assert {payload["tenant_id"] for payload in payloads} == {
        session["user"]["organizationId"]
    }
    assert {payload["document_id"] for payload in payloads} == {document["id"]}
    assert store.load(plan.plan_id) is not None

    # The existing active collection is still queryable after the target write.
    source_embedder = HashingEmbeddingProvider(dimension=384)
    query = await source_embedder.embed_query("separate target collection")
    source_hits = await app.state.vector_store.search(
        vector=query,
        tenant_id=session["user"]["organizationId"],
        top_k=10,
    )
    assert source_hits
    async with app.state.session_factory() as db:
        chunks_after = (
            await db.execute(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.document_id == uuid.UUID(document["id"]))
            )
        ).scalar_one()
    assert chunks_after == plan.total_chunks
