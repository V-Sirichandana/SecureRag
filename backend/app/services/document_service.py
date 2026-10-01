"""Document service — tenant-scoped CRUD with centralized authorization.

Every query is filtered by ``tenant_id``; a document from another tenant is
indistinguishable from one that does not exist (404).
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.core.permissions import Role, role_at_least
from app.models import Collection, Document, DocumentPermission, Membership, Tenant, User
from app.repositories import CollectionRepository, DocumentRepository
from app.schemas.document import (
    DocumentCreateIn,
    DocumentOut,
    DocumentPageOut,
    DocumentPermissionsIn,
    DocumentPermissionsOut,
    DocumentUpdateIn,
)
from app.services.audit_service import AuditService

DEFAULT_PAGE_TITLE = "Untitled"

# classifications that default to "everyone in the tenant" access
ORG_WIDE_CLASSIFICATIONS = {"public", "internal"}


def derive_file_type(name: str, explicit: str | None = None) -> str:
    if explicit:
        return explicit.lower().lstrip(".")[:16] or "txt"
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if re.fullmatch(r"[a-z0-9]{1,16}", extension):
        return extension
    return "txt"


class DocumentService:
    """Authorization rules (centralized):

    * OWNER / ADMIN            → full access to every tenant document
    * MANAGER                  → view/edit/delete any tenant document
    * MEMBER / VIEWER          → view documents they created, documents with an
                                 explicit grant (user or role), or org-wide
                                 (public/internal) documents; edit only their own
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = DocumentRepository(db)
        self.audit = AuditService(db)

    # ---------------------------------------------------------------- helpers
    async def _permissions(self, document_id: uuid.UUID) -> list[DocumentPermission]:
        result = await self.db.execute(
            select(DocumentPermission).where(DocumentPermission.document_id == document_id)
        )
        return list(result.scalars().all())

    @staticmethod
    def _can_view(
        role: Role,
        user_id: uuid.UUID,
        document: Document,
        grants: list[DocumentPermission],
    ) -> bool:
        if role_at_least(role, Role.ADMIN):
            return True
        if document.created_by == user_id:
            return True
        for grant in grants:
            if grant.user_id == user_id:
                return True
            if grant.role is not None and grant.role == role.value:
                return True
            if grant.user_id is None and grant.role is None:
                return True
        return False

    @staticmethod
    def _can_edit(role: Role, user_id: uuid.UUID, document: Document) -> bool:
        if not role_at_least(role, Role.MEMBER):
            return False
        if role_at_least(role, Role.MANAGER):
            return True
        return document.created_by == user_id

    def _serialize(
        self,
        document: Document,
        owner: User | None,
        collection: Collection | None,
    ) -> DocumentOut:
        return DocumentOut(
            id=str(document.id),
            name=document.name,
            file_type=document.file_type,
            size_bytes=document.file_size,
            collection_id=str(document.collection_id) if document.collection_id else None,
            collection_name=collection.name if collection else "Unfiled",
            owner=owner.name if owner else "",
            department=(owner.department if owner and owner.department else "General"),
            classification=document.classification,
            status=document.status,
            created_at=document.created_at,
            updated_at=document.updated_at,
            page_count=document.page_count,
            chunk_count=document.chunk_count,
            tags=document.tags or [],
        )

    # ----------------------------------------------------------------- queries
    async def list_documents(
        self,
        *,
        tenant: Tenant,
        user: User,
        role: Role,
        filters: dict,
        page: int = 1,
        page_size: int | None = None,
    ) -> tuple[list[DocumentOut], int]:
        visibility = None
        if not role_at_least(role, Role.ADMIN):
            # non-admins only see documents they are allowed to access
            visibility = (user.id, role.value)

        rows, total = await self.repository.list(
            tenant.id,
            visibility=visibility,
            offset=(page - 1) * (page_size or 50),
            limit=page_size,
            **filters,
        )
        items = [self._serialize(doc, owner, collection) for doc, owner, collection in rows]
        return items, total

    async def get_document(
        self,
        *,
        tenant: Tenant,
        user: User,
        role: Role,
        document_id: uuid.UUID,
    ) -> tuple[Document, User | None, Collection | None, DocumentOut]:
        row = await self.repository.get(tenant.id, document_id)
        if row is None:
            raise NotFoundError("DOCUMENT_NOT_FOUND")
        document, owner, collection = row
        if not self._can_view(role, user.id, document, await self._permissions(document.id)):
            # do not leak existence
            raise NotFoundError("DOCUMENT_NOT_FOUND")
        return document, owner, collection, self._serialize(document, owner, collection)

    # ---------------------------------------------------------------- commands
    async def create_document(
        self,
        *,
        tenant: Tenant,
        user: User,
        payload: DocumentCreateIn,
        ip_address: str | None,
        user_agent: str | None,
    ) -> DocumentOut:
        collection = await CollectionRepository(self.db).get(
            tenant.id, uuid.UUID(payload.collection_id)
        )
        if collection is None:
            raise NotFoundError("COLLECTION_NOT_FOUND")

        file_type = derive_file_type(payload.name, payload.file_type)
        document = Document(
            tenant_id=tenant.id,
            collection_id=collection.id,
            name=payload.name,
            file_name=payload.name,
            file_type=file_type,
            file_size=payload.size_bytes or 0,
            status="processing",
            classification=payload.classification,
            created_by=user.id,
            page_count=payload.page_count or 0,
            chunk_count=0,
            tags=[],
        )
        await self.repository.add(document)

        if payload.classification in ORG_WIDE_CLASSIFICATIONS:
            # global grant: everyone in the tenant may read this document
            self.db.add(DocumentPermission(document_id=document.id))

        await self.audit.log(
            user=user,
            tenant=tenant,
            action="DOCUMENT_UPLOAD",
            resource_type="document",
            resource_id=document.id,
            resource_label=document.name,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={
                "classification": document.classification,
                "collection": collection.name,
                "file_type": file_type,
            },
        )
        await self.db.commit()
        return self._serialize(document, user, collection)

    async def update_document(
        self,
        *,
        tenant: Tenant,
        user: User,
        role: Role,
        document_id: uuid.UUID,
        payload: DocumentUpdateIn,
        ip_address: str | None,
        user_agent: str | None,
    ) -> DocumentOut:
        row = await self.repository.get(tenant.id, document_id)
        if row is None:
            raise NotFoundError("DOCUMENT_NOT_FOUND")
        document, owner, collection = row

        if not self._can_view(role, user.id, document, await self._permissions(document.id)):
            raise NotFoundError("DOCUMENT_NOT_FOUND")
        if not self._can_edit(role, user.id, document):
            raise AppError("FORBIDDEN", "You cannot modify this document.", status_code=403)

        changed: dict[str, str] = {}
        if payload.name is not None and payload.name != document.name:
            changed["name"] = f"{document.name} -> {payload.name}"
            document.name = payload.name
            document.file_name = payload.name
        if payload.classification is not None:
            changed["classification"] = payload.classification
            document.classification = payload.classification
        if payload.status is not None:
            changed["status"] = payload.status
            document.status = payload.status
        if payload.collection_id is not None:
            target = await CollectionRepository(self.db).get(
                tenant.id, uuid.UUID(payload.collection_id)
            )
            if target is None:
                raise NotFoundError("COLLECTION_NOT_FOUND")
            changed["collection"] = target.name
            document.collection_id = target.id
            collection = target

        await self.audit.log(
            user=user,
            tenant=tenant,
            action="DOCUMENT_UPDATE",
            resource_type="document",
            resource_id=document.id,
            resource_label=document.name,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=changed,
        )
        await self.db.commit()
        return self._serialize(document, owner, collection)

    async def delete_document(
        self,
        *,
        tenant: Tenant,
        user: User,
        role: Role,
        document_id: uuid.UUID,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        row = await self.repository.get(tenant.id, document_id)
        if row is None:
            raise NotFoundError("DOCUMENT_NOT_FOUND")
        document, _, _ = row

        if not self._can_view(role, user.id, document, await self._permissions(document.id)):
            raise NotFoundError("DOCUMENT_NOT_FOUND")
        if not self._can_edit(role, user.id, document):
            raise AppError("FORBIDDEN", "You cannot delete this document.", status_code=403)

        await self.audit.log(
            user=user,
            tenant=tenant,
            action="DOCUMENT_DELETE",
            resource_type="document",
            resource_id=document.id,
            resource_label=document.name,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"classification": document.classification},
        )
        await self.repository.delete(document)
        await self.db.commit()

    async def update_permissions(
        self,
        *,
        tenant: Tenant,
        user: User,
        role: Role,
        document_id: uuid.UUID,
        payload: DocumentPermissionsIn,
        ip_address: str | None,
        user_agent: str | None,
    ) -> DocumentPermissionsOut:
        row = await self.repository.get(tenant.id, document_id)
        if row is None:
            raise NotFoundError("DOCUMENT_NOT_FOUND")
        document, _, _ = row

        if not self._can_view(role, user.id, document, await self._permissions(document.id)):
            raise NotFoundError("DOCUMENT_NOT_FOUND")
        if not role_at_least(role, Role.MANAGER):
            raise AppError(
                "INSUFFICIENT_ROLE",
                "Managing document permissions requires the MANAGER role or higher.",
                status_code=403,
            )

        targets = payload.targets
        normalized_roles: list[str] = []
        if payload.scope == "roles":
            normalized_roles = [Role.from_value(target).value for target in targets]
        elif payload.scope == "users":
            if targets:
                try:
                    parsed = {uuid.UUID(target) for target in targets}
                except ValueError as exc:
                    raise AppError(
                        "VALIDATION_ERROR",
                        "Invalid user id in targets.",
                        status_code=422,
                    ) from exc
                members = await self._member_ids(tenant.id)
                if not parsed.issubset(members):
                    raise AppError(
                        "VALIDATION_ERROR",
                        "All targets must be members of this organization.",
                        status_code=422,
                    )

        # replace existing grants
        existing = await self._permissions(document.id)
        for grant in existing:
            await self.db.delete(grant)
        await self.db.flush()

        if payload.scope in {"everyone", "members"}:
            self.db.add(DocumentPermission(document_id=document.id))
        elif payload.scope == "roles":
            for normalized in normalized_roles:
                self.db.add(DocumentPermission(document_id=document.id, role=normalized))
        else:  # users
            for target in targets:
                self.db.add(
                    DocumentPermission(document_id=document.id, user_id=uuid.UUID(target))
                )

        await self.audit.log(
            user=user,
            tenant=tenant,
            action="PERMISSION_CHANGED",
            resource_type="document",
            resource_id=document.id,
            resource_label=document.name,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"scope": payload.scope, "targets": str(len(targets))},
        )
        await self.db.commit()
        return DocumentPermissionsOut(id=str(document.id), scope=payload.scope, targets=targets)

    async def document_pages(
        self, *, tenant: Tenant, user: User, role: Role, document_id: uuid.UUID
    ) -> list[DocumentPageOut]:
        document, _, _, _ = await self.get_document(
            tenant=tenant, user=user, role=role, document_id=document_id
        )
        # Placeholder until the ingestion pipeline stores extracted text.
        page_count = max(document.page_count, 1)
        return [
            DocumentPageOut(
                page_number=index,
                title=f"{document.name} — page {index}" if page_count > 1 else document.name,
                paragraphs=[],
            )
            for index in range(1, page_count + 1)
        ]

    async def _member_ids(self, tenant_id: uuid.UUID) -> set[uuid.UUID]:
        result = await self.db.execute(
            select(Membership.user_id).where(Membership.tenant_id == tenant_id)
        )
        return {row for row in result.scalars()}
