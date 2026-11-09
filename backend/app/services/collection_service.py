"""Collection service — tenant-scoped CRUD."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.core.permissions import Role, role_at_least
from app.models import Collection, Tenant, User
from app.repositories import CollectionRepository, DocumentRepository, UserRepository
from app.schemas.collection import CollectionCreateIn, CollectionOut, CollectionUpdateIn
from app.services.audit_service import AuditService


class CollectionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = CollectionRepository(db)
        self.audit = AuditService(db)

    def _serialize(self, collection: Collection, owner: str, document_count: int) -> CollectionOut:
        return CollectionOut(
            id=str(collection.id),
            name=collection.name,
            description=collection.description,
            document_count=document_count,
            owner=owner,
            updated_at=collection.updated_at,
            visibility=collection.visibility,  # type: ignore[arg-type]
            color=collection.color,
        )

    async def _owner_names(self, collections: list[Collection]) -> dict[uuid.UUID, str]:
        names: dict[uuid.UUID, str] = {}
        for collection in collections:
            if collection.created_by and collection.created_by not in names:
                user = await UserRepository(self.db).get(collection.created_by)
                names[collection.created_by] = user.name if user else ""
        return names

    async def list_collections(self, *, tenant: Tenant) -> list[CollectionOut]:
        rows = await self.repository.list(tenant.id)
        owners = await self._owner_names([collection for collection, _ in rows])
        return [
            self._serialize(
                collection,
                owners.get(collection.created_by, ""),
                count,
            )
            for collection, count in rows
        ]

    async def get_collection(self, *, tenant: Tenant, collection_id: uuid.UUID) -> Collection:
        collection = await self.repository.get(tenant.id, collection_id)
        if collection is None:
            raise NotFoundError("COLLECTION_NOT_FOUND")
        return collection

    async def get_collection_out(
        self, *, tenant: Tenant, collection_id: uuid.UUID
    ) -> CollectionOut:
        collection = await self.get_collection(tenant=tenant, collection_id=collection_id)
        count = await self.repository.count_documents(collection.id)
        owner = ""
        if collection.created_by:
            creator = await UserRepository(self.db).get(collection.created_by)
            owner = creator.name if creator else ""
        return self._serialize(collection, owner, count)

    async def create_collection(
        self,
        *,
        tenant: Tenant,
        user: User,
        payload: CollectionCreateIn,
        ip_address: str | None,
        user_agent: str | None,
    ) -> CollectionOut:
        collection = Collection(
            tenant_id=tenant.id,
            name=payload.name,
            description=payload.description,
            visibility=payload.visibility,
            color=payload.color or "#6366f1",
            created_by=user.id,
        )
        await self.repository.add(collection)
        await self.audit.log(
            user=user,
            tenant=tenant,
            action="COLLECTION_CREATE",
            resource_type="collection",
            resource_id=collection.id,
            resource_label=collection.name,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"visibility": collection.visibility},
        )
        await self.db.commit()
        return self._serialize(collection, user.name, 0)

    async def update_collection(
        self,
        *,
        tenant: Tenant,
        user: User,
        role: Role,
        collection_id: uuid.UUID,
        payload: CollectionUpdateIn,
        ip_address: str | None,
        user_agent: str | None,
    ) -> CollectionOut:
        if not role_at_least(role, Role.MANAGER):
            raise AppError(
                "INSUFFICIENT_ROLE",
                "Updating collections requires the MANAGER role or higher.",
                status_code=403,
            )
        collection = await self.get_collection(tenant=tenant, collection_id=collection_id)

        changed: dict[str, str] = {}
        if payload.name is not None and payload.name != collection.name:
            changed["name"] = f"{collection.name} -> {payload.name}"
            collection.name = payload.name
        if payload.description is not None:
            changed["description"] = "updated"
            collection.description = payload.description
        if payload.visibility is not None:
            changed["visibility"] = payload.visibility
            collection.visibility = payload.visibility
        if payload.color is not None:
            collection.color = payload.color

        await self.audit.log(
            user=user,
            tenant=tenant,
            action="COLLECTION_UPDATE",
            resource_type="collection",
            resource_id=collection.id,
            resource_label=collection.name,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=changed,
        )
        await self.db.commit()
        owner = ""
        if collection.created_by:
            creator = await UserRepository(self.db).get(collection.created_by)
            owner = creator.name if creator else ""
        count = await self.repository.count_documents(collection.id)
        return self._serialize(collection, owner, count)

    async def delete_collection(
        self,
        *,
        tenant: Tenant,
        user: User,
        role: Role,
        collection_id: uuid.UUID,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        if not role_at_least(role, Role.MANAGER):
            raise AppError(
                "INSUFFICIENT_ROLE",
                "Deleting collections requires the MANAGER role or higher.",
                status_code=403,
            )
        collection = await self.get_collection(tenant=tenant, collection_id=collection_id)
        document_count = await DocumentRepository(self.db).count_in_collection(collection.id)
        await self.audit.log(
            user=user,
            tenant=tenant,
            action="COLLECTION_DELETE",
            resource_type="collection",
            resource_id=collection.id,
            resource_label=collection.name,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"documents": str(document_count)},
        )
        # documents survive; the FK sets their collection_id to NULL
        await self.repository.delete(collection)
        await self.db.commit()
