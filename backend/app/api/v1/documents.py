"""Document routes — tenant-scoped, with search/filter/pagination."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status

from app.core.dependencies import (
    AppSettings,
    CurrentMembership,
    CurrentTenant,
    CurrentUser,
    DbSession,
    StorageDep,
    VectorStoreDep,
    client_context,
    require_permission,
)
from app.schemas.document import (
    ClassificationLiteral,
    DocumentCreateIn,
    DocumentOut,
    DocumentPageOut,
    DocumentPermissionsIn,
    DocumentPermissionsOut,
    DocumentUpdateIn,
)
from app.services.document_service import DocumentService

documents_router = APIRouter(prefix="/documents", tags=["Documents"])


def _filters(
    search: Annotated[str | None, Query(alias="search")] = None,
    collection_id: Annotated[str | None, Query(alias="collectionId")] = None,
    department: Annotated[str | None, Query(alias="department")] = None,
    classification: Annotated[str | None, Query(alias="classification")] = None,
    file_type: Annotated[str | None, Query(alias="fileType")] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> dict:
    return {
        "search": search,
        "collection_id": collection_id,
        "department": department,
        "classification": classification,
        "file_type": file_type,
        "status": status_filter,
    }


@documents_router.get("", response_model=list[DocumentOut], summary="List documents")
async def list_documents(
    response: Response,
    tenant: CurrentTenant,
    user: CurrentUser,
    membership: CurrentMembership,
    db: DbSession,
    filters: Annotated[dict, Depends(_filters)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1, le=500, alias="pageSize")] = None,
) -> list[DocumentOut]:
    items, total = await DocumentService(db).list_documents(
        tenant=tenant,
        user=user,
        role=membership.role,
        filters=filters,
        page=page,
        page_size=page_size,
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@documents_router.post(
    "",
    response_model=DocumentOut,
    status_code=201,
    summary="Create a document (metadata first)",
    dependencies=[Depends(require_permission("upload_documents"))],
)
async def create_document(
    payload: DocumentCreateIn,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
) -> DocumentOut:
    ip_address, user_agent = client_context(request)
    return await DocumentService(db).create_document(
        tenant=tenant,
        user=user,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@documents_router.post(
    "/upload",
    response_model=DocumentOut,
    status_code=201,
    summary="Upload a file and index it for semantic search",
    dependencies=[Depends(require_permission("upload_documents"))],
)
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File(description="PDF, DOCX, TXT, MD, CSV or JSON")],
    collection_id: Annotated[str, Form()],
    tenant: CurrentTenant,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    vector_store: VectorStoreDep,
    storage: StorageDep,
    classification: Annotated[ClassificationLiteral, Form()] = "internal",
) -> DocumentOut:
    ip_address, user_agent = client_context(request)
    # bounded read: never buffer more than the configured limit
    content = await file.read(settings.max_upload_bytes + 1)
    return await DocumentService(
        db, settings=settings, vector_store=vector_store, storage=storage
    ).upload_document(
        tenant=tenant,
        user=user,
        collection_id=collection_id,
        classification=classification,
        file_name=file.filename or "",
        content=content,
        content_type=file.content_type,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@documents_router.post(
    "/{document_id}/content",
    response_model=DocumentOut,
    summary="Attach file content to an existing document and index it",
    dependencies=[Depends(require_permission("upload_documents"))],
)
async def upload_document_content(
    document_id: UUID,
    request: Request,
    file: Annotated[UploadFile, File(description="PDF, DOCX, TXT, MD, CSV or JSON")],
    tenant: CurrentTenant,
    user: CurrentUser,
    membership: CurrentMembership,
    db: DbSession,
    settings: AppSettings,
    vector_store: VectorStoreDep,
    storage: StorageDep,
) -> DocumentOut:
    ip_address, user_agent = client_context(request)
    content = await file.read(settings.max_upload_bytes + 1)
    return await DocumentService(
        db, settings=settings, vector_store=vector_store, storage=storage
    ).reingest_document(
        tenant=tenant,
        user=user,
        role=membership.role,
        document_id=document_id,
        file_name=file.filename or "",
        content=content,
        content_type=file.content_type,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@documents_router.get("/{document_id}", response_model=DocumentOut, summary="Fetch a document")
async def get_document(
    document_id: UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    membership: CurrentMembership,
    db: DbSession,
) -> DocumentOut:
    _, _, _, serialized = await DocumentService(db).get_document(
        tenant=tenant, user=user, role=membership.role, document_id=document_id
    )
    return serialized


@documents_router.patch(
    "/{document_id}",
    response_model=DocumentOut,
    summary="Update document metadata",
)
async def update_document(
    document_id: UUID,
    payload: DocumentUpdateIn,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    membership: CurrentMembership,
    db: DbSession,
) -> DocumentOut:
    ip_address, user_agent = client_context(request)
    return await DocumentService(db).update_document(
        tenant=tenant,
        user=user,
        role=membership.role,
        document_id=document_id,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@documents_router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
)
async def delete_document(
    document_id: UUID,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    membership: CurrentMembership,
    db: DbSession,
    vector_store: VectorStoreDep,
    storage: StorageDep,
) -> Response:
    ip_address, user_agent = client_context(request)
    await DocumentService(
        db, vector_store=vector_store, storage=storage
    ).delete_document(
        tenant=tenant,
        user=user,
        role=membership.role,
        document_id=document_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@documents_router.put(
    "/{document_id}/permissions",
    response_model=DocumentPermissionsOut,
    summary="Replace document access grants",
)
async def update_document_permissions(
    document_id: UUID,
    payload: DocumentPermissionsIn,
    request: Request,
    tenant: CurrentTenant,
    user: CurrentUser,
    membership: CurrentMembership,
    db: DbSession,
) -> DocumentPermissionsOut:
    ip_address, user_agent = client_context(request)
    return await DocumentService(db).update_permissions(
        tenant=tenant,
        user=user,
        role=membership.role,
        document_id=document_id,
        payload=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )


@documents_router.get(
    "/{document_id}/pages",
    response_model=list[DocumentPageOut],
    summary="Page structure for the document preview",
)
async def document_pages(
    document_id: UUID,
    tenant: CurrentTenant,
    user: CurrentUser,
    membership: CurrentMembership,
    db: DbSession,
) -> list[DocumentPageOut]:
    return await DocumentService(db).document_pages(
        tenant=tenant, user=user, role=membership.role, document_id=document_id
    )
