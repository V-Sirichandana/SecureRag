"""Audit routes — organization activity, ADMIN+ only."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.dependencies import CurrentTenant, DbSession, require_permission
from app.repositories import AuditRepository
from app.schemas.audit import AuditEventOut

audit_router = APIRouter(prefix="/audit", tags=["Audit"])


def _filters(
    user: Annotated[str | None, Query(alias="user")] = None,
    action: Annotated[str | None, Query(alias="action")] = None,
    resource: Annotated[str | None, Query(alias="resource")] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> dict:
    return {
        "actor": user,
        "action": action,
        "resource": resource,
        "status": status_filter,
    }


@audit_router.get(
    "",
    response_model=list[AuditEventOut],
    summary="List audit events",
    dependencies=[Depends(require_permission("view_audit_logs"))],
)
async def list_audit_events(
    response: Response,
    tenant: CurrentTenant,
    db: DbSession,
    filters: Annotated[dict, Depends(_filters)],
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditEventOut]:
    rows, total = await AuditRepository(db).list(
        tenant.id, offset=offset, limit=limit, **filters
    )
    response.headers["X-Total-Count"] = str(total)
    events: list[AuditEventOut] = []
    for entry, actor in rows:
        events.append(
            AuditEventOut(
                id=str(entry.id),
                timestamp=entry.created_at,
                user=actor.name if actor else "System",
                user_email=actor.email if actor else "",
                action=entry.action,
                resource=entry.resource_label or "",
                resource_type=entry.resource_type,
                ip_address=entry.ip_address or "",
                status=entry.status,  # type: ignore[arg-type]
                user_agent=entry.user_agent or "",
                metadata=entry.metadata_ or {},
            )
        )
    return events
