"""Global search across documents, collections and users (tenant-scoped).

Documents are additionally fenced by the SAME document-authorization
boundary as retrieval: non-admin callers only receive documents they are
allowed to view (``DocumentRepository.visibility_clause`` — the rule behind
``DocumentService._can_view``); ADMIN+ keeps full tenant-wide results.
"""

from __future__ import annotations

from sqlalchemy import or_, select

from app.core.exceptions import AppError
from app.core.permissions import Role, role_at_least
from app.models import Collection, Document, Membership, Tenant, User
from app.repositories import DocumentRepository
from app.schemas.settings import SearchResultOut


class SearchService:
    def __init__(self, db) -> None:
        self.db = db

    async def search(
        self,
        *,
        tenant: Tenant,
        user: User,
        role: Role,
        query: str,
        limit: int = 5,
    ) -> list[SearchResultOut]:
        q = query.strip()
        if not q:
            return []
        if len(q) > 200:
            raise AppError("VALIDATION_ERROR", "Search query is too long.", status_code=422)

        pattern = f"%{q}%"
        results: list[SearchResultOut] = []

        # server-derived identity only: non-admins see exactly the documents
        # they are authorized to view (same predicate as retrieval)
        visibility = None
        if not role_at_least(role, Role.ADMIN):
            visibility = (user.id, role.value)

        doc_query = (
            select(Document, Collection.name)
            .outerjoin(Collection, Document.collection_id == Collection.id)
            .where(Document.tenant_id == tenant.id, Document.name.ilike(pattern))
        )
        if visibility is not None:
            doc_query = doc_query.where(DocumentRepository.visibility_clause(*visibility))
        doc_rows = (
            await self.db.execute(
                doc_query.order_by(Document.created_at.desc()).limit(5)
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
            count_query = select(Document.id).where(Document.collection_id == collection.id)
            if visibility is not None:
                count_query = count_query.where(
                    DocumentRepository.visibility_clause(*visibility)
                )
            count = (await self.db.execute(count_query)).all()
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
        for member in users:
            results.append(
                SearchResultOut(
                    id=str(member.id),
                    title=member.name,
                    subtitle=member.email,
                    type="user",
                    href="/app/users",
                )
            )

        return results
