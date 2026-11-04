"""Repository helpers — all tenant-owned queries take ``tenant_id``."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    Collection,
    Document,
    DocumentPermission,
    Membership,
    Tenant,
    User,
)


def ilike(column: Any, value: str) -> Any:
    return column.ilike(f"%{value}%")


class TenantRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, tenant_id: uuid.UUID) -> Tenant | None:
        return await self.db.get(Tenant, tenant_id)

    async def slug_taken(self, slug: str) -> bool:
        result = await self.db.execute(select(Tenant.id).where(Tenant.slug == slug))
        return result.scalar_one_or_none() is not None

    async def add(self, tenant: Tenant) -> Tenant:
        self.db.add(tenant)
        await self.db.flush()
        return tenant


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def get_by_password_reset_token_hash(self, token_hash: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.password_reset_token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def add(self, user: User) -> User:
        self.db.add(user)
        await self.db.flush()
        return user

    async def membership(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> Membership | None:
        result = await self.db.execute(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def memberships_with_tenants(self, user_id: uuid.UUID) -> list[tuple[Membership, Tenant]]:
        result = await self.db.execute(
            select(Membership, Tenant)
            .join(Tenant, Membership.tenant_id == Tenant.id)
            .where(Membership.user_id == user_id)
            .order_by(Membership.created_at)
        )
        return list(result.all())

    async def members(self, tenant_id: uuid.UUID) -> list[tuple[Membership, User]]:
        """All members of a tenant — the ONLY membership source is the DB."""
        result = await self.db.execute(
            select(Membership, User)
            .join(User, Membership.user_id == User.id)
            .where(Membership.tenant_id == tenant_id)
            .order_by(User.name)
        )
        return list(result.all())

    async def member_count(self, tenant_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count(Membership.id)).where(Membership.tenant_id == tenant_id)
        )
        return int(result.scalar_one())

    async def owner_count(self, tenant_id: uuid.UUID) -> int:
        from app.core.permissions import Role

        result = await self.db.execute(
            select(func.count(Membership.id)).where(
                Membership.tenant_id == tenant_id,
                Membership.role == Role.OWNER,
            )
        )
        return int(result.scalar_one())

    async def add_membership(self, membership: Membership) -> Membership:
        self.db.add(membership)
        await self.db.flush()
        return membership

    async def delete_membership(self, membership: Membership) -> None:
        await self.db.delete(membership)
        await self.db.flush()


class CollectionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _with_counts(self) -> Select:
        return (
            select(Collection, func.count(Document.id).label("document_count"))
            .outerjoin(Document, Document.collection_id == Collection.id)
            .group_by(Collection.id)
        )

    async def list(self, tenant_id: uuid.UUID) -> list[tuple[Collection, int]]:
        result = await self.db.execute(
            self._with_counts()
            .where(Collection.tenant_id == tenant_id)
            .order_by(Collection.updated_at.desc())
        )
        return [(row[0], int(row[1])) for row in result.all()]

    async def get(self, tenant_id: uuid.UUID, collection_id: uuid.UUID) -> Collection | None:
        result = await self.db.execute(
            select(Collection).where(
                Collection.id == collection_id,
                Collection.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def count_documents(self, collection_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count(Document.id)).where(Document.collection_id == collection_id)
        )
        return int(result.scalar_one())

    async def add(self, collection: Collection) -> Collection:
        self.db.add(collection)
        await self.db.flush()
        return collection

    async def delete(self, collection: Collection) -> None:
        await self.db.delete(collection)
        await self.db.flush()


class DocumentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _base() -> Select:
        return (
            select(Document, User, Collection)
            .outerjoin(User, Document.created_by == User.id)
            .outerjoin(Collection, Document.collection_id == Collection.id)
        )

    @staticmethod
    def visibility_clause(user_id: uuid.UUID, role_value: str):
        """Rows the viewer may read: own documents, explicit grants, org-wide."""
        perm_user = (
            select(DocumentPermission.id)
            .where(
                DocumentPermission.document_id == Document.id,
                DocumentPermission.user_id == user_id,
            )
            .exists()
        )
        perm_role = (
            select(DocumentPermission.id)
            .where(
                DocumentPermission.document_id == Document.id,
                DocumentPermission.role == role_value,
            )
            .exists()
        )
        perm_global = (
            select(DocumentPermission.id)
            .where(
                DocumentPermission.document_id == Document.id,
                DocumentPermission.user_id.is_(None),
                DocumentPermission.role.is_(None),
            )
            .exists()
        )
        return or_(Document.created_by == user_id, perm_user, perm_role, perm_global)

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        search: str | None = None,
        collection_id: str | None = None,
        department: str | None = None,
        classification: str | None = None,
        file_type: str | None = None,
        status: str | None = None,
        visibility: tuple[uuid.UUID, str] | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> tuple[list[tuple[Document, User | None, Collection | None]], int]:
        """Return ``(rows, total)`` scoped to the tenant.

        ``visibility=(user_id, role)`` additionally restricts rows to documents
        the viewer may access (explicit grant, own document, or org-wide grant).
        """
        query = self._base().where(Document.tenant_id == tenant_id)
        if visibility is not None:
            query = query.where(self.visibility_clause(*visibility))
        if search:
            query = query.where(
                or_(ilike(Document.name, search), ilike(User.name, search))
            )
        if collection_id and collection_id != "all":
            query = query.where(Document.collection_id == uuid.UUID(collection_id))
        if department and department != "all":
            query = query.where(User.department == department)
        if classification and classification != "all":
            query = query.where(Document.classification == classification)
        if file_type and file_type != "all":
            query = query.where(Document.file_type == file_type)
        if status and status != "all":
            query = query.where(Document.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total = int((await self.db.execute(count_query)).scalar_one())

        query = query.order_by(Document.created_at.desc()).offset(offset)
        if limit is not None:
            query = query.limit(limit)
        rows = list((await self.db.execute(query)).all())
        return rows, total

    async def get(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> tuple[Document, User | None, Collection | None] | None:
        """Tenant-scoped fetch — returns None for other tenants' documents."""
        query = self._base().where(
            Document.id == document_id,
            Document.tenant_id == tenant_id,
        )
        row = (await self.db.execute(query)).one_or_none()
        return row if row else None

    async def add(self, document: Document) -> Document:
        self.db.add(document)
        await self.db.flush()
        return document

    async def delete(self, document: Document) -> None:
        await self.db.delete(document)
        await self.db.flush()

    async def total_size(self, tenant_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.coalesce(func.sum(Document.file_size), 0)).where(
                Document.tenant_id == tenant_id
            )
        )
        return int(result.scalar_one())

    async def count(self, tenant_id: uuid.UUID, *, since: Any | None = None) -> int:
        query = select(func.count(Document.id)).where(Document.tenant_id == tenant_id)
        if since is not None:
            query = query.where(Document.created_at >= since)
        return int((await self.db.execute(query)).scalar_one())

    async def count_in_collection(self, collection_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count(Document.id)).where(Document.collection_id == collection_id)
        )
        return int(result.scalar_one())


class AuditRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, entry: AuditLog) -> AuditLog:
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        actor: str | None = None,
        action: str | None = None,
        resource: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> tuple[list[tuple[AuditLog, User | None]], int]:
        query = (
            select(AuditLog, User)
            .outerjoin(User, AuditLog.user_id == User.id)
            .where(AuditLog.tenant_id == tenant_id)
        )
        if actor:
            query = query.where(
                or_(ilike(User.name, actor), ilike(User.email, actor))
            )
        if action and action != "all":
            query = query.where(AuditLog.action == action)
        if resource:
            query = query.where(
                or_(
                    ilike(AuditLog.resource_label, resource),
                    ilike(AuditLog.resource_id, resource),
                )
            )
        if status and status != "all":
            query = query.where(AuditLog.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total = int((await self.db.execute(count_query)).scalar_one())

        query = query.order_by(AuditLog.created_at.desc()).offset(offset)
        if limit is not None:
            query = query.limit(limit)
        rows = list((await self.db.execute(query)).all())
        return rows, total

    async def count_actions(
        self,
        tenant_id: uuid.UUID,
        *,
        actions: tuple[str, ...],
        since: Any | None = None,
        until: Any | None = None,
    ) -> int:
        query = select(func.count(AuditLog.id)).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action.in_(actions),
        )
        if since is not None:
            query = query.where(AuditLog.created_at >= since)
        if until is not None:
            query = query.where(AuditLog.created_at < until)
        return int((await self.db.execute(query)).scalar_one())


from app.repositories.chat import ApiKeyRepository, ConversationRepository  # noqa: E402

__all__ = [
    "ApiKeyRepository",
    "AuditRepository",
    "CollectionRepository",
    "ConversationRepository",
    "DocumentRepository",
    "TenantRepository",
    "UserRepository",
]
