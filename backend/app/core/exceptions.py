"""Consistent API error handling.

Every error response has the same envelope::

    {
      "detail": "<human readable message>",
      "error": {"code": "DOCUMENT_NOT_FOUND", "message": "<same message>", ...}
    }

``detail`` is included because the existing Next.js client reads it directly;
``error`` is the canonical machine-readable shape. Internal stack traces are
never exposed to clients — they are logged server-side only.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("securerag.errors")

# default message per machine-readable error code
DEFAULT_MESSAGES: dict[str, str] = {
    "AUTH_REQUIRED": "Authentication is required.",
    "AUTH_TOKEN_INVALID": "The provided token is invalid.",
    "AUTH_TOKEN_EXPIRED": "The provided token has expired.",
    "INVALID_CREDENTIALS": "Invalid email or password.",
    "ACCOUNT_DISABLED": "This account has been deactivated.",
    "PASSWORD_RESET_NOT_IMPLEMENTED": "Password reset emails are not configured yet.",
    "OAUTH_NOT_CONFIGURED": "This sign-in provider is not configured yet.",
    "NO_MEMBERSHIP": "This user does not belong to any organization yet.",
    "TENANT_ACCESS_DENIED": "You are not a member of the requested organization.",
    "INSUFFICIENT_ROLE": "Your role does not permit this action.",
    "FORBIDDEN": "You do not have permission to perform this action.",
    "NOT_FOUND": "The requested resource was not found.",
    "VALIDATION_ERROR": "The request payload failed validation.",
    "EMAIL_EXISTS": "An account with this email already exists.",
    "SLUG_CONFLICT": "An organization with this name already exists.",
    "TENANT_NOT_FOUND": "The requested organization was not found.",
    "USER_NOT_FOUND": "The requested user was not found.",
    "COLLECTION_NOT_FOUND": "The requested collection was not found.",
    "COLLECTION_NOT_EMPTY": "The collection still contains documents.",
    "DOCUMENT_NOT_FOUND": "The requested document was not found.",
    "UNSUPPORTED_FILE_TYPE": "This file type is not supported.",
    "EMPTY_DOCUMENT": "The uploaded file contains no extractable text.",
    "DOCUMENT_UNREADABLE": "The uploaded file could not be read.",
    "FILE_TOO_LARGE": "The uploaded file exceeds the maximum allowed size.",
    "CONVERSATION_NOT_FOUND": "The requested conversation was not found.",
    "MESSAGE_NOT_FOUND": "The requested message was not found.",
    "API_KEY_NOT_FOUND": "The requested API key was not found.",
    "LAST_OWNER": "An organization must keep at least one owner.",
    "CANNOT_MODIFY_SELF": "You cannot perform this action on your own account.",
    "INVITE_INVALID": "This invitation link is not valid.",
    "INVITE_EXPIRED": "This invitation link has expired. Ask an admin to send a new one.",
    "INVITE_ALREADY_ACCEPTED": "This invitation has already been accepted.",
    "ROLE_INVALID": "Unknown role.",
    "CONFLICT": "The request conflicts with the current state.",
    "TOO_MANY_REQUESTS": "Too many attempts. Please try again later.",
    "SERVICE_NOT_CONFIGURED": "This service is not configured yet.",
    "SERVICE_UNAVAILABLE": "This service is temporarily unavailable.",
    "DATABASE_ERROR": "The request could not be completed.",
    "INTERNAL_ERROR": "An unexpected error occurred.",
}

STATUS_FOR_CODE: dict[str, int] = {
    "AUTH_REQUIRED": 401,
    "AUTH_TOKEN_INVALID": 401,
    "AUTH_TOKEN_EXPIRED": 401,
    "INVALID_CREDENTIALS": 401,
    "ACCOUNT_DISABLED": 403,
    "FORBIDDEN": 403,
    "INSUFFICIENT_ROLE": 403,
    "TENANT_ACCESS_DENIED": 403,
    "NO_MEMBERSHIP": 403,
    "NOT_FOUND": 404,
    "VALIDATION_ERROR": 422,
    "EMPTY_DOCUMENT": 422,
    "DOCUMENT_UNREADABLE": 422,
    "ROLE_INVALID": 422,
    "CONFLICT": 409,
    "EMAIL_EXISTS": 409,
    "SLUG_CONFLICT": 409,
    "LAST_OWNER": 409,
    "INVITE_ALREADY_ACCEPTED": 409,
    "INVITE_INVALID": 400,
    "INVITE_EXPIRED": 400,
    "FILE_TOO_LARGE": 413,
    "UNSUPPORTED_FILE_TYPE": 415,
    "TOO_MANY_REQUESTS": 429,
    "SERVICE_NOT_CONFIGURED": 501,
    "SERVICE_UNAVAILABLE": 503,
    "OAUTH_NOT_CONFIGURED": 501,
    "DATABASE_ERROR": 500,
    "INTERNAL_ERROR": 500,
}

HTTP_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_ERROR",
    501: "NOT_IMPLEMENTED",
    503: "SERVICE_UNAVAILABLE",
}


class AppError(Exception):
    """Application error carrying a machine-readable code and HTTP status."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        status_code: int | None = None,
        details: object | None = None,
    ) -> None:
        self.code = code
        self.message = message or DEFAULT_MESSAGES.get(code, "The request failed.")
        self.status_code = status_code or STATUS_FOR_CODE.get(code, 400)
        self.details = details
        super().__init__(self.message)


class NotFoundError(AppError):
    def __init__(self, code: str = "NOT_FOUND", message: str | None = None) -> None:
        super().__init__(code, message, status_code=404)


class AuthenticationError(AppError):
    def __init__(self, code: str = "AUTH_REQUIRED", message: str | None = None) -> None:
        super().__init__(code, message, status_code=401)


class AuthorizationError(AppError):
    def __init__(self, code: str = "FORBIDDEN", message: str | None = None) -> None:
        super().__init__(code, message, status_code=403)


class ConflictError(AppError):
    def __init__(self, code: str = "CONFLICT", message: str | None = None) -> None:
        super().__init__(code, message, status_code=409)


class RateLimitError(AppError):
    def __init__(self, code: str = "TOO_MANY_REQUESTS", message: str | None = None) -> None:
        super().__init__(code, message, status_code=429)


class ServiceNotConfiguredError(AppError):
    def __init__(self, code: str = "SERVICE_NOT_CONFIGURED", message: str | None = None) -> None:
        super().__init__(code, message, status_code=501)


def error_payload(code: str, message: str, details: object | None = None) -> dict:
    error: dict = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"detail": message, "error": error}


def _validation_summary(exc: RequestValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors()[:5]:
        location = ".".join(str(item) for item in err.get("loc", ()) if item != "body")
        field = location or "payload"
        parts.append(f"{field}: {err.get('msg', 'invalid')}")
    return "Validation failed — " + "; ".join(parts)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_payload(
                "VALIDATION_ERROR",
                _validation_summary(exc),
                details=exc.errors(),
            ),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("Integrity error on %s %s: %s", request.method, request.url.path, exc.orig)
        return JSONResponse(
            status_code=409,
            content=error_payload("CONFLICT", DEFAULT_MESSAGES["CONFLICT"]),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTP_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
        detail = exc.detail if isinstance(exc.detail, str) else "The request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(code, detail),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=error_payload("INTERNAL_ERROR", DEFAULT_MESSAGES["INTERNAL_ERROR"]),
        )
