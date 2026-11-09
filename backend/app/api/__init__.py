"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.api_keys import api_keys_router
from app.api.v1.audit import audit_router
from app.api.v1.auth import auth_router
from app.api.v1.chat import chat_router
from app.api.v1.collections import collections_router
from app.api.v1.documents import documents_router
from app.api.v1.search import search_router
from app.api.v1.settings import settings_router
from app.api.v1.tenants import tenants_router
from app.api.v1.usage import usage_router
from app.api.v1.users import users_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(tenants_router)
api_router.include_router(users_router)
api_router.include_router(documents_router)
api_router.include_router(collections_router)
api_router.include_router(chat_router)
api_router.include_router(audit_router)
api_router.include_router(api_keys_router)
api_router.include_router(usage_router)
api_router.include_router(settings_router)
api_router.include_router(search_router)

__all__ = ["api_router"]
