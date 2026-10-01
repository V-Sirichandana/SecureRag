"""Password hashing, JWT issuing/verification and API key generation."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

from app.core.config import Settings
from app.core.exceptions import AppError

# OWASP-aligned Argon2id parameters (kept modest for fast test suites).
_hasher = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1)

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
INVITE_TOKEN_TYPE = "invite"
INVITE_TOKEN_EXPIRE_DAYS = 7


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def _create_token(
    user_id: uuid.UUID, token_type: str, lifetime: timedelta, settings: Settings
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),  # JWT contains only the user id
        "type": token_type,
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: uuid.UUID, settings: Settings) -> str:
    return _create_token(
        user_id,
        ACCESS_TOKEN_TYPE,
        timedelta(minutes=settings.access_token_expire_minutes),
        settings,
    )


def create_refresh_token(user_id: uuid.UUID, settings: Settings) -> str:
    return _create_token(
        user_id,
        REFRESH_TOKEN_TYPE,
        timedelta(days=settings.refresh_token_expire_days),
        settings,
    )


def create_invite_token(user_id: uuid.UUID, settings: Settings) -> str:
    """Single-purpose token handed to an invitee so they can set a password.

    It only ever proves "this holder was invited" — it grants no session on
    its own and becomes useless the moment the account is activated.
    """
    return _create_token(
        user_id,
        INVITE_TOKEN_TYPE,
        timedelta(days=INVITE_TOKEN_EXPIRE_DAYS),
        settings,
    )


def decode_token(token: str, settings: Settings, expected_type: str) -> uuid.UUID:
    """Decode a JWT and return the user id.

    Raises AppError(401) for expired or invalid tokens, or a token issued
    with the wrong purpose (e.g. refresh token used as access token).
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AppError("AUTH_TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise AppError("AUTH_TOKEN_INVALID") from exc

    if payload.get("type") != expected_type:
        raise AppError("AUTH_TOKEN_INVALID", "Token has the wrong purpose.")
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AppError("AUTH_TOKEN_INVALID", "Token subject is missing.") from exc


def generate_api_key(environment: str) -> tuple[str, str]:
    """Return ``(raw_key, key_hash)``.

    The raw key is shown to the caller exactly once; only the hash is stored.
    """
    prefix = "sk_live_" if environment == "live" else "sk_test_"
    raw = f"{prefix}{secrets.token_urlsafe(32)}"
    return raw, hash_api_key(raw)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def mask_api_key(environment: str) -> str:
    """Display mask matching the frontend's ``maskedKey`` format."""
    prefix = "sk_live_" if environment == "live" else "sk_test_"
    return f"{prefix}{'•' * 16}"
