"""Private document byte storage.

Two adapters implement the same interface:

* :class:`LocalStorage` — the existing filesystem layout
  ``STORAGE_DIR/<tenant_id>/<document_id>.<ext>``. New writes return the
  absolute path; legacy rows that stored a relative or absolute path are
  still readable/deletable without migration.
* :class:`S3Storage` — optional S3-compatible object storage. Object keys are
  server-generated (``<tenant_id>/<document_id>.<ext>``), never client paths.
  The adapter never generates public URLs, presigned URLs or public ACLs;
  the configured bucket is expected to remain private.

Storage failures are reported as generic :class:`StorageError` (503) values so
provider credentials, endpoints and object paths never reach clients or logs.
"""

from __future__ import annotations

import asyncio
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.core.config import Settings
from app.core.exceptions import AppError, ServiceNotConfiguredError
from app.services.ingestion.processor import file_extension

_SUFFIX_RE = re.compile(r"^[a-z0-9]{1,16}$")
_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}


class StorageError(AppError):
    """Operational storage failure — generic message, no provider details."""

    def __init__(self, message: str = "The document storage operation failed.") -> None:
        super().__init__("SERVICE_UNAVAILABLE", message, status_code=503)


@runtime_checkable
class Storage(Protocol):
    async def save(
        self,
        *,
        tenant_id: uuid.UUID | str,
        document_id: uuid.UUID | str,
        file_name: str,
        content: bytes,
    ) -> str:
        """Persist bytes under a server-generated tenant-scoped key."""
        ...

    async def read(self, storage_path: str) -> bytes:
        """Return the stored bytes for a path/key produced by :meth:`save`."""
        ...

    async def delete(self, storage_path: str) -> None:
        """Delete a stored object; deleting a missing object is a no-op."""
        ...

    async def exists(self, storage_path: str) -> bool:
        """Return whether a stored object is present."""
        ...


def _identifier(value: object) -> str:
    """Normalize a server-generated UUID and reject anything path-like."""
    try:
        return str(uuid.UUID(str(value)))
    except (AttributeError, TypeError, ValueError):
        raise StorageError("Invalid storage identifier.") from None


def _safe_suffix(file_name: str) -> str:
    suffix = file_extension(file_name)
    return suffix if _SUFFIX_RE.fullmatch(suffix) else ""


def _object_name(document_id: str, file_name: str) -> str:
    suffix = _safe_suffix(file_name)
    return f"{document_id}{f'.{suffix}' if suffix else ''}"


class LocalStorage:
    """Existing local filesystem behavior behind the storage interface."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    async def save(
        self,
        *,
        tenant_id: uuid.UUID | str,
        document_id: uuid.UUID | str,
        file_name: str,
        content: bytes,
    ) -> str:
        tenant = _identifier(tenant_id)
        document = _identifier(document_id)
        target = self.root / tenant / _object_name(document, file_name)
        try:
            await asyncio.to_thread(self._write, target, content)
        except OSError:
            raise StorageError("The document could not be stored.") from None
        return str(target)

    @staticmethod
    def _write(target: Path, content: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def _resolve(self, storage_path: str) -> Path:
        if not isinstance(storage_path, str) or not storage_path.strip():
            raise StorageError("Invalid storage path.")
        try:
            candidate = Path(storage_path).expanduser()
            if candidate.is_absolute():
                resolved = candidate.resolve(strict=False)
            else:
                # Legacy rows may hold a path relative to the process CWD
                # (the previous local implementation). Accept it when it is
                # already inside the configured root; otherwise treat the
                # value as a root-relative key.
                legacy = candidate.resolve(strict=False)
                resolved = (
                    legacy
                    if self._within(legacy)
                    else (self.root / candidate).resolve(strict=False)
                )
        except OSError:
            raise StorageError("Invalid storage path.") from None
        if not self._within(resolved):
            raise StorageError("Invalid storage path.")
        return resolved

    def _within(self, path: Path) -> bool:
        try:
            path.relative_to(self.root)
        except ValueError:
            return False
        return True

    async def read(self, storage_path: str) -> bytes:
        target = self._resolve(storage_path)
        try:
            return await asyncio.to_thread(target.read_bytes)
        except OSError:
            raise StorageError("The stored document could not be read.") from None

    async def delete(self, storage_path: str) -> None:
        target = self._resolve(storage_path)
        try:
            await asyncio.to_thread(target.unlink, missing_ok=True)
        except OSError:
            raise StorageError("The stored document could not be removed.") from None

    async def exists(self, storage_path: str) -> bool:
        target = self._resolve(storage_path)
        try:
            return await asyncio.to_thread(target.is_file)
        except OSError:
            raise StorageError("The stored document could not be checked.") from None


class S3Storage:
    """Optional S3-compatible adapter with an injectable client for tests.

    The bucket must be private. This adapter performs only object-level
    ``put``/``get``/``head``/``delete`` calls and never creates public ACLs,
    public URLs or presigned URLs.
    """

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str = "",
        region: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
        client: Any | None = None,
    ) -> None:
        self.bucket = (bucket or "").strip()
        if not self.bucket:
            raise ServiceNotConfiguredError(
                "SERVICE_NOT_CONFIGURED",
                "STORAGE_BUCKET is not configured for S3 storage.",
            )
        if bool(access_key_id) != bool(secret_access_key):
            raise ServiceNotConfiguredError(
                "SERVICE_NOT_CONFIGURED",
                "STORAGE_ACCESS_KEY_ID and STORAGE_SECRET_ACCESS_KEY "
                "must be configured together.",
            )
        self.endpoint_url = (endpoint_url or "").strip()
        self.region = (region or "").strip()
        self._access_key_id = (access_key_id or "").strip()
        self._secret_access_key = (secret_access_key or "").strip()
        self._client = client
        self._client_lock = threading.Lock()

    def __repr__(self) -> str:  # never include credentials
        return f"S3Storage(bucket={self.bucket!r})"

    def _build_client(self) -> Any:
        try:
            import boto3
        except ImportError:
            raise ServiceNotConfiguredError(
                "SERVICE_NOT_CONFIGURED",
                "S3 storage requires the optional 'boto3' package.",
            ) from None
        options: dict[str, Any] = {"service_name": "s3"}
        if self.region:
            options["region_name"] = self.region
        if self.endpoint_url:
            options["endpoint_url"] = self.endpoint_url
        if self._access_key_id:
            options["aws_access_key_id"] = self._access_key_id
            options["aws_secret_access_key"] = self._secret_access_key
        try:
            return boto3.client(**options)
        except Exception:
            raise ServiceNotConfiguredError(
                "SERVICE_NOT_CONFIGURED",
                "The S3 storage client could not be configured.",
            ) from None

    def _client_instance(self) -> Any:
        if self._client is not None:
            return self._client
        with self._client_lock:
            if self._client is None:
                self._client = self._build_client()
        return self._client

    def _key(self, tenant_id: uuid.UUID | str, document_id: uuid.UUID | str, file_name: str) -> str:
        tenant = _identifier(tenant_id)
        document = _identifier(document_id)
        return f"{tenant}/{_object_name(document, file_name)}"

    async def _call(self, method: str, **kwargs: Any) -> Any:
        client = await asyncio.to_thread(self._client_instance)
        try:
            return await asyncio.to_thread(getattr(client, method), **kwargs)
        except ServiceNotConfiguredError:
            raise
        except Exception:
            raise StorageError() from None

    async def save(
        self,
        *,
        tenant_id: uuid.UUID | str,
        document_id: uuid.UUID | str,
        file_name: str,
        content: bytes,
    ) -> str:
        key = self._key(tenant_id, document_id, file_name)
        await self._call(
            "put_object",
            Bucket=self.bucket,
            Key=key,
            Body=content,
        )
        return key

    async def read(self, storage_path: str) -> bytes:
        if not isinstance(storage_path, str) or not storage_path.strip():
            raise StorageError("Invalid storage path.")
        response = await self._call("get_object", Bucket=self.bucket, Key=storage_path)
        body = response.get("Body") if isinstance(response, dict) else None
        if body is None:
            raise StorageError("The stored document could not be read.")

        def _read_body() -> bytes:
            data = body.read() if hasattr(body, "read") else body
            if not isinstance(data, (bytes, bytearray)):
                raise StorageError("The stored document could not be read.")
            return bytes(data)

        try:
            return await asyncio.to_thread(_read_body)
        except StorageError:
            raise
        except Exception:
            raise StorageError("The stored document could not be read.") from None

    async def delete(self, storage_path: str) -> None:
        if not isinstance(storage_path, str) or not storage_path.strip():
            raise StorageError("Invalid storage path.")
        await self._call("delete_object", Bucket=self.bucket, Key=storage_path)

    async def exists(self, storage_path: str) -> bool:
        if not isinstance(storage_path, str) or not storage_path.strip():
            raise StorageError("Invalid storage path.")
        client = await asyncio.to_thread(self._client_instance)
        try:
            await asyncio.to_thread(
                client.head_object, Bucket=self.bucket, Key=storage_path
            )
        except Exception as exc:
            if _is_not_found(exc):
                return False
            raise StorageError("The stored document could not be checked.") from None
        return True


def _is_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error")
        code = str(error.get("Code", "")) if isinstance(error, dict) else ""
        metadata = response.get("ResponseMetadata")
        status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
        return code in _NOT_FOUND_CODES or status == 404
    return isinstance(exc, FileNotFoundError)


class UnconfiguredStorage:
    """Startup-safe stand-in used when the configured storage is incomplete.

    Reads/writes report ``SERVICE_NOT_CONFIGURED`` (501) on use. Deletes are
    a no-op so document metadata can still be cleaned up.
    """

    def __init__(self, reason: str = "Document storage is not configured.") -> None:
        self.reason = reason

    def _raise(self) -> None:
        raise ServiceNotConfiguredError("SERVICE_NOT_CONFIGURED", self.reason)

    async def save(
        self,
        *,
        tenant_id: uuid.UUID | str,
        document_id: uuid.UUID | str,
        file_name: str,
        content: bytes,
    ) -> str:
        self._raise()

    async def read(self, storage_path: str) -> bytes:
        self._raise()

    async def delete(self, storage_path: str) -> None:
        return None

    async def exists(self, storage_path: str) -> bool:
        self._raise()


def get_storage(settings: Settings) -> Storage:
    """Build the configured storage adapter (strict: missing config raises)."""
    provider = (settings.storage_provider or "").strip().lower()
    if provider == "local":
        return LocalStorage(settings.storage_dir)
    if provider == "s3":
        return S3Storage(
            bucket=settings.storage_bucket,
            endpoint_url=settings.storage_endpoint_url,
            region=settings.storage_region,
            access_key_id=settings.storage_access_key_id,
            secret_access_key=settings.storage_secret_access_key,
        )
    raise ServiceNotConfiguredError(
        "SERVICE_NOT_CONFIGURED",
        f"Storage provider '{provider}' is unknown. Set STORAGE_PROVIDER to 'local' or 's3'.",
    )


def build_storage(settings: Settings) -> Storage:
    """Startup variant: never raises, reports configuration errors on use."""
    try:
        return get_storage(settings)
    except ServiceNotConfiguredError as exc:
        return UnconfiguredStorage(str(exc))


__all__ = [
    "LocalStorage",
    "S3Storage",
    "Storage",
    "StorageError",
    "UnconfiguredStorage",
    "build_storage",
    "get_storage",
]
