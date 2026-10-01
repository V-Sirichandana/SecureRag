"""Global search across documents, collections and users (tenant-scoped)."""

from __future__ import annotations

from sqlalchemy import or_, select

from app.core.exceptions import AppError
from app.models import Collection, Document, Membership, Tenant, User
from app.schemas.settings import SearchResultOut


class SearchService:
    def __init__(self, db) -> None:
        self.db = db

    async def search(self, *, tenant: Tenant, query: str, limit: int = 5) -> list[SearchResultOut]:
        q = query.strip()
        if not q:
            return []
        if len(q) > 200:
            raise AppError("VALIDATION_ERROR", "Search query is too long.", status_code=422)

        pattern = f"%{q}%"
        results: list[SearchResultOut] = []

        doc_rows = (
            await self.db.execute(
                select(Document, Collection.name)
                .outerjoin(Collection, Document.collection_id == Collection.id)
                .where(Document.tenant_id == tenant.id, Document.name.ilike(pattern))
                .order_by(Document.created_at.desc())
                .limit(5)
            )
        ).all()
        for document, collection_name in doc_rows:
            results.append(
                SearchResultOut(
                    id=str(document.id),
                    title=document.name,
                    subtitle=f"{collection_name or 'Unfiled'} · {document.file_type.upper()}",
                    type="document",
                    href=f"/app/documents/{document.id}",
                )
            )

        collections = (
            await self.db.execute(
                select(Collection)
                .where(Collection.tenant_id == tenant.id, Collection.name.ilike(pattern))
                .order_by(Collection.updated_at.desc())
                .limit(4)
            )
        ).scalars().all()
        for collection in collections:
            count = (
                await self.db.execute(
                    select(Document.id).where(Document.collection_id == collection.id)
                )
            ).all()
            results.append(
                SearchResultOut(
                    id=str(collection.id),
                    title=collection.name,
                    subtitle=f"{len(count)} documents",
                    type="collection",
                    href="/app/collections",
                )
            )

        users = (
            await self.db.execute(
                select(User)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    Membership.tenant_id == tenant.id,
                    or_(User.name.ilike(pattern), User.email.ilike(pattern)),
                )
                .limit(4)
            )
        ).scalars().all()
        for user in users:
            results.append(
                SearchResultOut(
                    id=str(user.id),
                    title=user.name,
                    subtitle=user.email,
                    type="user",
                    href="/app/users",
                )
            )

        return results
