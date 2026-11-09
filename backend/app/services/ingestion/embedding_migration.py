"""Non-destructive embedding migration support.

This module is deliberately **not** wired into startup or request handling.
It provides the pieces an operator (or a separately deployed migration worker)
uses to move an existing corpus to a new semantic embedding model without
touching the active collection:

* :func:`build_embedding_migration_plan` performs read-only database and Qdrant
  inspection and produces a per-document plan.
* :func:`reembed_document` can copy one document's stored chunks into a
  **separate target collection**, using the target model. It never writes to
  the source collection, never deletes source vectors/documents, and does not
  change permissions.
* :class:`MigrationProgressStore` records completed documents, chunk counts
  and safe failure messages as JSON for auditable, operator-driven runs.
* :func:`validate_embedding_migration` checks the target collection dimension
  and point count before an operator switches traffic.

Traffic cutover is intentionally out of scope: the active collection is
changed only by an explicit configuration change (``QDRANT_COLLECTION`` plus
matching ``EMBEDDING_*`` settings) after validation. No code here mutates
``Settings`` or the live collection.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError, ServiceNotConfiguredError
from app.models import Document, DocumentChunk
from app.services.ingestion.vector_store import MEMORY_URL, build_tenant_filter
from app.services.rag.base import EmbeddingService, VectorStore

logger = logging.getLogger("securerag.embedding_migration")

PROGRESS_PLANNED = "planned"
PROGRESS_RUNNING = "running"
PROGRESS_COMPLETED = "completed"
PROGRESS_VALIDATED = "validated"
PROGRESS_FAILED = "failed"

_MAX_ERROR_LENGTH = 300
_MAX_COLLECTION_NAME_LENGTH = 255
_COLLECTION_SEGMENT_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class EmbeddingProfile:
    """Identity of an embedding space: provider + model + vector dimension."""

    provider: str
    model: str
    dimension: int

    def __post_init__(self) -> None:
        provider = (self.provider or "").strip().lower()
        model = (self.model or "").strip()
        if not provider:
            raise ValueError("embedding profile provider must not be empty")
        if not model:
            raise ValueError("embedding profile model must not be empty")
        if self.dimension < 1:
            raise ValueError("embedding profile dimension must be positive")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "dimension", int(self.dimension))

    @property
    def signature(self) -> str:
        return f"{self.provider}:{self.model}:{self.dimension}"

    @classmethod
    def from_service(
        cls, service: EmbeddingService, *, provider: str | None = None
    ) -> EmbeddingProfile:
        provider_name = (
            provider
            or getattr(service, "provider_name", "")
            or getattr(service, "model_name", "")
            or ""
        )
        model_name = getattr(service, "model_name", "") or provider_name
        return cls(
            provider=str(provider_name),
            model=str(model_name),
            dimension=int(service.dimension),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "dimension": self.dimension,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EmbeddingProfile:
        return cls(
            provider=str(value["provider"]),
            model=str(value["model"]),
            dimension=int(value["dimension"]),
        )


def embedding_profile_from_settings(settings: Settings) -> EmbeddingProfile:
    """Resolve and validate the configured provider's profile (no model load)."""
    from app.services.rag import get_embedding_service  # local: avoid import cycle

    service = get_embedding_service(settings)
    return EmbeddingProfile.from_service(service, provider=settings.embedding_provider)


def _collection_segment(value: str, *, limit: int) -> str:
    cleaned = _COLLECTION_SEGMENT_RE.sub("_", value.strip()).strip("_")
    return (cleaned or "embedding")[:limit]


def build_target_collection_name(
    source_collection: str, target_profile: EmbeddingProfile
) -> str:
    """Derive a deterministic, Qdrant-safe collection name for a new model.

    The source name is retained as a prefix for operator readability, but the
    target name includes the provider, model, dimension and a short profile
    hash, so two models with the same dimension can never collide.
    """
    source = _collection_segment(source_collection or "securerag", limit=80)
    model = _collection_segment(target_profile.model, limit=48)
    digest = hashlib.sha256(target_profile.signature.encode("utf-8")).hexdigest()[:8]
    name = (
        f"{source}__{target_profile.provider}__{model}__"
        f"{target_profile.dimension}__{digest}"
    )
    return name[:_MAX_COLLECTION_NAME_LENGTH]


@dataclass(frozen=True)
class CollectionInfo:
    """Read-only Qdrant collection metadata."""

    name: str
    dimension: int | None
    point_count: int | None = None


@runtime_checkable
class CollectionCatalog(Protocol):
    """Read-only metadata reader used by the planner and validator."""

    def inspect(
        self, name: str, *, tenant_id: str | None = None
    ) -> CollectionInfo | None:
        ...


class QdrantCollectionCatalog:
    """Read-only Qdrant metadata adapter.

    It never creates, updates or deletes a collection. Construction with
    ``:memory:`` creates a separate empty embedded client (the application's
    in-memory store is not shared across client instances); use a real Qdrant
    server for an actual migration plan.
    """

    def __init__(
        self, *, url: str, api_key: str = "", client: Any | None = None
    ) -> None:
        if client is not None:
            self._client = client
            return
        if not url:
            raise ServiceNotConfiguredError(
                "SERVICE_NOT_CONFIGURED", "QDRANT_URL is not configured."
            )
        from qdrant_client import QdrantClient  # local: optional migration path

        if url == MEMORY_URL:
            self._client = QdrantClient(location=MEMORY_URL)
        else:
            self._client = QdrantClient(url=url, api_key=api_key or None)

    @classmethod
    def from_settings(cls, settings: Settings) -> QdrantCollectionCatalog:
        return cls(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

    def inspect(
        self, name: str, *, tenant_id: str | None = None
    ) -> CollectionInfo | None:
        if not self._client.collection_exists(name):
            return None
        info = self._client.get_collection(name)
        vectors = info.config.params.vectors
        dimension = None if isinstance(vectors, dict) else int(vectors.size)
        count_filter = build_tenant_filter(tenant_id) if tenant_id else None
        counted = self._client.count(
            collection_name=name, count_filter=count_filter, exact=True
        )
        return CollectionInfo(
            name=name, dimension=dimension, point_count=int(counted.count)
        )


@dataclass(frozen=True)
class MigrationDocument:
    tenant_id: str
    document_id: str
    chunk_count: int
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "document_id": self.document_id,
            "chunk_count": self.chunk_count,
            "status": self.status,
        }


@dataclass
class EmbeddingMigrationPlan:
    source_collection: str
    target_collection: str
    source_profile: EmbeddingProfile
    target_profile: EmbeddingProfile
    tenant_id: str | None
    documents: list[MigrationDocument]
    source_info: CollectionInfo | None = None
    target_info: CollectionInfo | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_documents(self) -> int:
        return len(self.documents)

    @property
    def total_chunks(self) -> int:
        return sum(document.chunk_count for document in self.documents)

    @property
    def plan_id(self) -> str:
        material = (
            f"{self.source_collection}|{self.target_collection}|"
            f"{self.tenant_id or '*'}|{self.target_profile.signature}"
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    @property
    def can_start(self) -> bool:
        return not self.errors and self.total_documents > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "source_collection": self.source_collection,
            "target_collection": self.target_collection,
            "source_profile": self.source_profile.to_dict(),
            "target_profile": self.target_profile.to_dict(),
            "tenant_id": self.tenant_id,
            "total_documents": self.total_documents,
            "total_chunks": self.total_chunks,
            "documents": [document.to_dict() for document in self.documents],
            "source_info": None
            if self.source_info is None
            else {
                "name": self.source_info.name,
                "dimension": self.source_info.dimension,
                "point_count": self.source_info.point_count,
            },
            "target_info": None
            if self.target_info is None
            else {
                "name": self.target_info.name,
                "dimension": self.target_info.dimension,
                "point_count": self.target_info.point_count,
            },
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def _normalize_tenant_id(tenant_id: str | None) -> str | None:
    if tenant_id is None:
        return None
    try:
        return str(uuid.UUID(str(tenant_id)))
    except ValueError as exc:
        raise AppError(
            "VALIDATION_ERROR", "tenant_id must be a valid UUID."
        ) from exc


async def _inspect(
    catalog: CollectionCatalog, name: str, *, tenant_id: str | None
) -> CollectionInfo | None:
    return await asyncio.to_thread(
        catalog.inspect, name, tenant_id=tenant_id
    )


async def build_embedding_migration_plan(
    *,
    db: AsyncSession,
    target_profile: EmbeddingProfile,
    settings: Settings | None = None,
    source_profile: EmbeddingProfile | None = None,
    source_collection: str | None = None,
    target_collection: str | None = None,
    tenant_id: str | None = None,
    catalog: CollectionCatalog | None = None,
) -> EmbeddingMigrationPlan:
    """Build a read-only migration plan.

    Exactly one of ``settings`` or ``source_profile`` must be supplied. The
    function reads document/chunk counts and Qdrant collection metadata only;
    it performs no writes and never touches the active collection.

    ``tenant_id`` scopes the plan to one tenant. When omitted, an operator-level
    plan covers every tenant; each document still retains its own server-side
    ``tenant_id`` for re-embedding and retrieval filtering.
    """
    if source_profile is None:
        if settings is None:
            raise ValueError("settings or source_profile is required")
        source_profile = embedding_profile_from_settings(settings)

    if source_collection is None:
        if settings is None:
            raise ValueError("source_collection is required without settings")
        source_collection = settings.qdrant_collection
    source_collection = source_collection.strip() or "securerag"

    if catalog is None:
        if settings is None:
            raise ValueError("catalog or settings is required")
        catalog = QdrantCollectionCatalog.from_settings(settings)

    tenant_id = _normalize_tenant_id(tenant_id)
    target_collection = (
        target_collection.strip()
        if target_collection
        else build_target_collection_name(source_collection, target_profile)
    )
    if not target_collection:
        raise ValueError("target_collection must not be empty")

    errors: list[str] = []
    warnings: list[str] = []
    if target_collection == source_collection:
        errors.append("target_collection must be different from source_collection")
    if target_profile == source_profile:
        errors.append("target_profile must differ from source_profile")

    tenant_uuid = uuid.UUID(tenant_id) if tenant_id else None
    conditions = [Document.tenant_id == tenant_uuid] if tenant_uuid else []
    stmt = (
        select(
            Document.tenant_id,
            Document.id,
            Document.status,
            func.count(DocumentChunk.id),
        )
        .join(
            DocumentChunk,
            and_(
                DocumentChunk.document_id == Document.id,
                DocumentChunk.tenant_id == Document.tenant_id,
            ),
        )
        .where(*conditions)
        .group_by(Document.tenant_id, Document.id, Document.status)
        .order_by(Document.tenant_id, Document.id)
    )
    rows = (await db.execute(stmt)).all()
    documents = [
        MigrationDocument(
            tenant_id=str(row[0]),
            document_id=str(row[1]),
            chunk_count=int(row[3]),
            status=str(row[2]),
        )
        for row in rows
    ]

    empty_stmt = (
        select(func.count())
        .select_from(Document)
        .outerjoin(
            DocumentChunk,
            and_(
                DocumentChunk.document_id == Document.id,
                DocumentChunk.tenant_id == Document.tenant_id,
            ),
        )
        .where(DocumentChunk.id.is_(None), *conditions)
    )
    documents_without_chunks = int((await db.execute(empty_stmt)).scalar_one())
    if documents_without_chunks:
        warnings.append(
            f"{documents_without_chunks} document(s) have no stored chunks and "
            "cannot be re-embedded."
        )

    by_status: dict[str, int] = {}
    for document in documents:
        by_status[document.status] = by_status.get(document.status, 0) + 1
    if any(status != "ready" for status in by_status):
        warnings.append(
            "The plan includes non-ready documents; verify their stored chunks "
            "before cutover."
        )

    source_info = await _inspect(catalog, source_collection, tenant_id=tenant_id)
    target_info = await _inspect(catalog, target_collection, tenant_id=tenant_id)
    if source_info is None:
        warnings.append(
            f"Source collection '{source_collection}' was not found; re-embedding "
            "uses the stored document chunks, but verify the source profile."
        )
    elif source_info.dimension is not None and (
        source_info.dimension != source_profile.dimension
    ):
        errors.append(
            f"Source collection '{source_collection}' has dimension "
            f"{source_info.dimension}, but the configured source profile expects "
            f"{source_profile.dimension}."
        )

    if target_info is not None:
        if target_info.dimension is None:
            errors.append(
                f"Target collection '{target_collection}' uses named vectors; "
                "this migration supports one unnamed vector per point."
            )
        elif target_info.dimension != target_profile.dimension:
            errors.append(
                f"Target collection '{target_collection}' has dimension "
                f"{target_info.dimension}, but the target profile expects "
                f"{target_profile.dimension}."
            )
        if (
            target_info.point_count is not None
            and target_info.point_count > sum(item.chunk_count for item in documents)
        ):
            warnings.append(
                f"Target collection already contains {target_info.point_count} "
                "point(s); validation will require an exact count for this scope."
            )
    else:
        warnings.append(
            f"Target collection '{target_collection}' does not exist yet; the "
            "explicit migration step will create it with dimension "
            f"{target_profile.dimension}."
        )

    if not documents:
        warnings.append("No documents with stored chunks match this migration scope.")

    return EmbeddingMigrationPlan(
        source_collection=source_collection,
        target_collection=target_collection,
        source_profile=source_profile,
        target_profile=target_profile,
        tenant_id=tenant_id,
        documents=documents,
        source_info=source_info,
        target_info=target_info,
        warnings=warnings,
        errors=errors,
    )


@dataclass(frozen=True)
class MigrationFailure:
    tenant_id: str
    document_id: str
    error: str

    def to_dict(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "document_id": self.document_id,
            "error": self.error,
        }


@dataclass
class MigrationProgress:
    """Serializable progress and failure journal for one migration plan."""

    plan_id: str
    source_collection: str
    target_collection: str
    source_profile: EmbeddingProfile
    target_profile: EmbeddingProfile
    tenant_id: str | None
    total_documents: int
    total_chunks: int
    status: str = PROGRESS_PLANNED
    completed_documents: int = 0
    failed_documents: int = 0
    completed_chunks: int = 0
    failures: list[MigrationFailure] = field(default_factory=list)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def from_plan(cls, plan: EmbeddingMigrationPlan) -> MigrationProgress:
        return cls(
            plan_id=plan.plan_id,
            source_collection=plan.source_collection,
            target_collection=plan.target_collection,
            source_profile=plan.source_profile,
            target_profile=plan.target_profile,
            tenant_id=plan.tenant_id,
            total_documents=plan.total_documents,
            total_chunks=plan.total_chunks,
        )

    def _touch(self) -> None:
        self.updated_at = _now()
        if self.completed_documents + self.failed_documents >= self.total_documents:
            self.status = PROGRESS_COMPLETED
        else:
            self.status = PROGRESS_RUNNING

    def record_success(self, document: MigrationDocument) -> None:
        self.completed_documents += 1
        self.completed_chunks += document.chunk_count
        self._touch()

    def record_failure(
        self, document: MigrationDocument, error: str
    ) -> None:
        self.failed_documents += 1
        safe = re.sub(r"\s+", " ", str(error or "unknown error")).strip()
        self.failures.append(
            MigrationFailure(
                tenant_id=document.tenant_id,
                document_id=document.document_id,
                error=safe[:_MAX_ERROR_LENGTH],
            )
        )
        self._touch()

    def mark_validated(self, *, ok: bool) -> None:
        if not ok:
            raise ValueError("migration validation must pass before cutover")
        if self.failed_documents or self.failures:
            raise ValueError("a migration with failures cannot be validated")
        if self.completed_documents != self.total_documents:
            raise ValueError("all documents must be processed before validation")
        self.status = PROGRESS_VALIDATED
        self.updated_at = _now()

    @property
    def ready_for_cutover(self) -> bool:
        return (
            self.status == PROGRESS_VALIDATED
            and self.failed_documents == 0
            and self.completed_documents == self.total_documents
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "source_collection": self.source_collection,
            "target_collection": self.target_collection,
            "source_profile": self.source_profile.to_dict(),
            "target_profile": self.target_profile.to_dict(),
            "tenant_id": self.tenant_id,
            "total_documents": self.total_documents,
            "total_chunks": self.total_chunks,
            "status": self.status,
            "completed_documents": self.completed_documents,
            "failed_documents": self.failed_documents,
            "completed_chunks": self.completed_chunks,
            "failures": [failure.to_dict() for failure in self.failures],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> MigrationProgress:
        return cls(
            plan_id=str(value["plan_id"]),
            source_collection=str(value["source_collection"]),
            target_collection=str(value["target_collection"]),
            source_profile=EmbeddingProfile.from_dict(value["source_profile"]),
            target_profile=EmbeddingProfile.from_dict(value["target_profile"]),
            tenant_id=value.get("tenant_id"),
            total_documents=int(value["total_documents"]),
            total_chunks=int(value["total_chunks"]),
            status=str(value["status"]),
            completed_documents=int(value["completed_documents"]),
            failed_documents=int(value["failed_documents"]),
            completed_chunks=int(value["completed_chunks"]),
            failures=[
                MigrationFailure(
                    tenant_id=str(item["tenant_id"]),
                    document_id=str(item["document_id"]),
                    error=str(item["error"]),
                )
                for item in value.get("failures", [])
            ],
            updated_at=str(value["updated_at"]),
        )


class MigrationProgressStore:
    """Atomic JSON journal for migration progress and failures.

    The store is explicitly opt-in; no application path writes it. Keeping the
    journal outside the database guarantees that planning/re-embedding cannot
    modify document or permission rows.
    """

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)

    @classmethod
    def for_settings(cls, settings: Settings) -> MigrationProgressStore:
        return cls(Path(settings.storage_dir) / "embedding_migrations")

    def path_for(self, plan_id: str) -> Path:
        return self.state_dir / f"{plan_id}.json"

    def save(self, progress: MigrationProgress) -> Path:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        target = self.path_for(progress.plan_id)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(progress.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, target)
        return target

    def load(self, plan_id: str) -> MigrationProgress | None:
        path = self.path_for(plan_id)
        if not path.exists():
            return None
        return MigrationProgress.from_dict(
            json.loads(path.read_text(encoding="utf-8"))
        )


def _validate_executor_target(
    plan: EmbeddingMigrationPlan,
    *,
    embedder: EmbeddingService,
    target_store: VectorStore,
) -> None:
    if plan.errors:
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED",
            "The migration plan has validation errors: " + "; ".join(plan.errors),
        )
    if plan.target_collection == plan.source_collection:
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED",
            "The migration target must be a separate collection.",
        )
    if embedder.dimension != plan.target_profile.dimension:
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED",
            f"The migration embedder produces {embedder.dimension} dimensions, "
            f"but the target profile requires {plan.target_profile.dimension}.",
        )
    model_name = str(getattr(embedder, "model_name", "") or "").strip()
    if model_name and model_name.casefold() != plan.target_profile.model.casefold():
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED",
            f"The migration embedder model '{model_name}' does not match the "
            f"target profile '{plan.target_profile.model}'.",
        )
    provider_name = str(getattr(embedder, "provider_name", "") or "").strip()
    if provider_name and provider_name.casefold() != plan.target_profile.provider.casefold():
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED",
            f"The migration embedder provider '{provider_name}' does not match "
            f"the target profile '{plan.target_profile.provider}'.",
        )
    target_name = getattr(target_store, "collection_name", None)
    if target_name and str(target_name) != plan.target_collection:
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED",
            f"The target store is bound to '{target_name}', not the planned "
            f"target '{plan.target_collection}'.",
        )


def _chunk_payload(document: Document, chunk: DocumentChunk) -> dict[str, Any]:
    """Payload copied from the source-of-truth DB rows.

    ACL hints are intentionally absent: retrieval always checks the CURRENT
    ``documents`` / ``document_permissions`` rows, so a migration can neither
    preserve nor widen stale permissions.
    """
    return {
        "chunk_id": chunk.chunk_id,
        "tenant_id": str(chunk.tenant_id),
        "document_id": str(chunk.document_id),
        "collection_id": str(chunk.collection_id) if chunk.collection_id else None,
        "chunk_index": chunk.chunk_index,
        "page": chunk.page,
        "filename": chunk.filename,
        "text": chunk.text,
        "name": document.name,
        "classification": document.classification,
        "created_by": str(document.created_by) if document.created_by else None,
    }


async def reembed_document(
    *,
    db: AsyncSession,
    plan: EmbeddingMigrationPlan,
    document: MigrationDocument,
    embedder: EmbeddingService,
    target_store: VectorStore,
    progress: MigrationProgress,
    progress_store: MigrationProgressStore | None = None,
    batch_size: int = 32,
) -> bool:
    """Re-embed one document into the separate target collection.

    This is an explicit operator/worker step, never called automatically. It
    reads canonical chunks from PostgreSQL, writes only to ``target_store``,
    and records success or a safe failure message. The source collection is
    never read, written, or deleted by this function.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    _validate_executor_target(plan, embedder=embedder, target_store=target_store)
    if plan.tenant_id is not None and document.tenant_id != plan.tenant_id:
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED",
            "The document is outside the migration plan's tenant scope.",
        )

    tenant_uuid = uuid.UUID(document.tenant_id)
    document_uuid = uuid.UUID(document.document_id)
    row = await db.get(Document, document_uuid)
    if row is None or row.tenant_id != tenant_uuid:
        progress.record_failure(document, "Document was not found in its tenant.")
        if progress_store:
            await asyncio.to_thread(progress_store.save, progress)
        return False

    chunks = list(
        (
            await db.execute(
                select(DocumentChunk)
                .where(
                    DocumentChunk.tenant_id == tenant_uuid,
                    DocumentChunk.document_id == document_uuid,
                )
                .order_by(DocumentChunk.chunk_index)
            )
        )
        .scalars()
        .all()
    )
    if len(chunks) != document.chunk_count:
        progress.record_failure(
            document,
            "Stored chunk count changed since planning; rebuild the plan.",
        )
        if progress_store:
            await asyncio.to_thread(progress_store.save, progress)
        return False
    if not chunks:
        progress.record_failure(document, "Document has no stored chunks.")
        if progress_store:
            await asyncio.to_thread(progress_store.save, progress)
        return False

    try:
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = await embedder.embed_documents([chunk.text for chunk in batch])
            if len(vectors) != len(batch):
                raise AppError(
                    "SERVICE_UNAVAILABLE",
                    "The embedding model returned an unexpected number of vectors.",
                )
            payloads = [_chunk_payload(row, chunk) for chunk in batch]
            await target_store.upsert_chunks(
                vectors=vectors,
                payloads=payloads,
                vector_size=embedder.dimension,
            )
    except AppError as exc:
        progress.record_failure(document, exc.message)
        if progress_store:
            await asyncio.to_thread(progress_store.save, progress)
        return False
    except Exception:  # noqa: BLE001 - track failure without leaking internals
        logger.exception(
            "Embedding migration failed for document %s", document.document_id
        )
        progress.record_failure(document, "Unexpected migration failure.")
        if progress_store:
            await asyncio.to_thread(progress_store.save, progress)
        return False

    progress.record_success(document)
    if progress_store:
        await asyncio.to_thread(progress_store.save, progress)
    return True


@dataclass(frozen=True)
class MigrationValidation:
    ok: bool
    errors: tuple[str, ...]
    target_point_count: int | None
    expected_chunks: int
    checked_at: str = field(default_factory=_now)


async def validate_embedding_migration(
    plan: EmbeddingMigrationPlan,
    *,
    catalog: CollectionCatalog,
    progress: MigrationProgress | None = None,
) -> MigrationValidation:
    """Validate target dimension/count before any traffic switch.

    Read-only: the active collection and configuration are never modified. A
    target with a missing collection, wrong dimension, missing/extra points,
    or an incomplete/failed progress journal cannot pass validation.
    """
    errors: list[str] = list(plan.errors)
    info = await _inspect(catalog, plan.target_collection, tenant_id=plan.tenant_id)
    if info is None:
        errors.append(f"Target collection '{plan.target_collection}' does not exist.")
        point_count = None
    else:
        point_count = info.point_count
        if info.dimension is None:
            errors.append("Target collection uses named vectors; one unnamed vector is required.")
        elif info.dimension != plan.target_profile.dimension:
            errors.append(
                f"Target dimension {info.dimension} does not match the target "
                f"profile ({plan.target_profile.dimension})."
            )
        if point_count is None:
            errors.append("Target collection point count is unavailable.")
        elif point_count != plan.total_chunks:
            errors.append(
                f"Target has {point_count} point(s), expected {plan.total_chunks}."
            )

    if progress is not None:
        if progress.plan_id != plan.plan_id:
            errors.append("Progress journal belongs to a different plan.")
        if progress.failed_documents or progress.failures:
            errors.append("The migration recorded one or more failed documents.")
        if progress.completed_documents != plan.total_documents:
            errors.append(
                f"Only {progress.completed_documents} of {plan.total_documents} "
                "document(s) completed."
            )
        if progress.completed_chunks != plan.total_chunks:
            errors.append(
                f"{progress.completed_chunks} of {plan.total_chunks} chunk(s) completed."
            )

    return MigrationValidation(
        ok=not errors,
        errors=tuple(errors),
        target_point_count=point_count,
        expected_chunks=plan.total_chunks,
    )


__all__ = [
    "CollectionCatalog",
    "CollectionInfo",
    "EmbeddingMigrationPlan",
    "EmbeddingProfile",
    "MigrationDocument",
    "MigrationFailure",
    "MigrationProgress",
    "MigrationProgressStore",
    "MigrationValidation",
    "PROGRESS_COMPLETED",
    "PROGRESS_FAILED",
    "PROGRESS_PLANNED",
    "PROGRESS_RUNNING",
    "PROGRESS_VALIDATED",
    "QdrantCollectionCatalog",
    "build_embedding_migration_plan",
    "build_target_collection_name",
    "embedding_profile_from_settings",
    "reembed_document",
    "validate_embedding_migration",
]
