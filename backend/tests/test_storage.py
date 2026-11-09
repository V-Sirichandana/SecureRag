"""Private document storage: local regression, S3 adapter, tenancy and failures.

The S3 adapter is exercised with an injected fake client — no boto3 install,
network call, bucket or credentials are required.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings
from app.core.exceptions import ServiceNotConfiguredError
from app.db.database import create_all, drop_all
from app.main import create_app
from app.models import Document
from app.services.storage import (
    LocalStorage,
    S3Storage,
    StorageError,
    UnconfiguredStorage,
    build_storage,
    get_storage,
)
from tests.conftest import auth, create_collection, make_client, register

TEST_JWT = "test-secret-key-not-for-production"
S3_SECRET = "super-secret-storage-key"


# --------------------------------------------------------------- S3 fake client
class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _NotFound(Exception):
    response = {
        "Error": {"Code": "404"},
        "ResponseMetadata": {"HTTPStatusCode": 404},
    }


class _FakeS3Client:
    def __init__(self, *, fail_on: str | None = None, message: str = "") -> None:
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple[str, dict]] = []
        self.fail_on = fail_on
        self.message = message

    def _fail(self, operation: str) -> None:
        if self.fail_on == operation:
            raise RuntimeError(self.message)

    def put_object(self, **kwargs):
        self._fail("put_object")
        self.calls.append(("put_object", kwargs))
        self.objects[kwargs["Key"]] = kwargs["Body"]
        return {}

    def get_object(self, **kwargs):
        self._fail("get_object")
        self.calls.append(("get_object", kwargs))
        if kwargs["Key"] not in self.objects:
            raise _NotFound
        return {"Body": _Body(self.objects[kwargs["Key"]])}

    def head_object(self, **kwargs):
        self._fail("head_object")
        self.calls.append(("head_object", kwargs))
        if kwargs["Key"] not in self.objects:
            raise _NotFound
        return {}

    def delete_object(self, **kwargs):
        self._fail("delete_object")
        self.calls.append(("delete_object", kwargs))
        self.objects.pop(kwargs["Key"], None)
        return {}


# --------------------------------------------------------------- local storage
async def test_local_storage_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    tenant, document = uuid.uuid4(), uuid.uuid4()

    key = await storage.save(
        tenant_id=tenant,
        document_id=document,
        file_name="handbook.txt",
        content=b"private handbook bytes",
    )
    assert Path(key) == (tmp_path / "uploads" / str(tenant) / f"{document}.txt")
    assert await storage.exists(key)
    assert await storage.read(key) == b"private handbook bytes"

    await storage.delete(key)
    assert not await storage.exists(key)
    await storage.delete(key)  # deleting a missing object is a no-op


async def test_local_storage_tenant_path_separation(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    document = uuid.uuid4()

    key_a = await storage.save(
        tenant_id=tenant_a,
        document_id=document,
        file_name="a.txt",
        content=b"tenant a",
    )
    key_b = await storage.save(
        tenant_id=tenant_b,
        document_id=document,
        file_name="b.txt",
        content=b"tenant b",
    )

    assert Path(key_a).parent.parent == (tmp_path / "uploads").resolve()
    assert Path(key_a).parent.name == str(tenant_a)
    assert Path(key_b).parent.name == str(tenant_b)
    assert Path(key_a) != Path(key_b)
    assert await storage.read(key_a) == b"tenant a"
    assert await storage.read(key_b) == b"tenant b"


async def test_local_storage_rejects_path_traversal(tmp_path):
    storage = LocalStorage(tmp_path / "uploads")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"must not be readable")

    with pytest.raises(StorageError):
        await storage.read(str(outside))
    with pytest.raises(StorageError):
        await storage.exists(str(outside))
    with pytest.raises(StorageError):
        await storage.delete(str(outside))
    with pytest.raises(StorageError):
        await storage.read("../outside.txt")
    with pytest.raises(StorageError):
        await storage.save(
            tenant_id="../evil",
            document_id=uuid.uuid4(),
            file_name="x.txt",
            content=b"x",
        )


async def test_local_storage_reads_legacy_relative_and_absolute_paths(
    tmp_path, monkeypatch
):
    """Existing rows are not migrated and remain readable/deletable."""
    root = tmp_path / "uploads"
    tenant, document = uuid.uuid4(), uuid.uuid4()
    legacy = root / str(tenant) / f"{document}.txt"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"legacy bytes")
    monkeypatch.chdir(tmp_path)

    storage = LocalStorage(root)
    relative = Path("uploads") / str(tenant) / f"{document}.txt"
    assert await storage.read(str(relative)) == b"legacy bytes"
    assert await storage.read(str(legacy)) == b"legacy bytes"
    await storage.delete(str(relative))
    assert not legacy.exists()


async def test_local_storage_failure_is_a_generic_storage_error(tmp_path):
    not_a_directory = tmp_path / "blocked"
    not_a_directory.write_text("file, not a directory")
    storage = LocalStorage(not_a_directory)

    with pytest.raises(StorageError) as excinfo:
        await storage.save(
            tenant_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            file_name="x.txt",
            content=b"x",
        )
    assert excinfo.value.status_code == 503
    assert await storage.exists(str(not_a_directory / "missing")) is False


# ----------------------------------------------------------------- S3 adapter
async def test_s3_storage_roundtrip_with_mocked_client():
    client = _FakeS3Client()
    storage = S3Storage(bucket="private-docs", client=client)
    tenant, document = uuid.uuid4(), uuid.uuid4()

    key = await storage.save(
        tenant_id=tenant,
        document_id=document,
        file_name="handbook.txt",
        content=b"object bytes",
    )
    assert key == f"{tenant}/{document}.txt"
    assert await storage.exists(key)
    assert await storage.read(key) == b"object bytes"

    await storage.delete(key)
    assert not await storage.exists(key)
    assert [name for name, _ in client.calls] == [
        "put_object",
        "head_object",
        "get_object",
        "delete_object",
        "head_object",
    ]


async def test_s3_storage_uses_private_server_generated_tenant_keys():
    client = _FakeS3Client()
    storage = S3Storage(bucket="private-docs", client=client)
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    document = uuid.uuid4()

    key_a = await storage.save(
        tenant_id=tenant_a,
        document_id=document,
        file_name="../../escape.txt",
        content=b"a",
    )
    key_b = await storage.save(
        tenant_id=tenant_b,
        document_id=document,
        file_name="b.txt",
        content=b"b",
    )

    assert key_a.startswith(f"{tenant_a}/")
    assert key_b.startswith(f"{tenant_b}/")
    assert key_a != key_b
    assert ".." not in key_a and "\\" not in key_a
    put_calls = [payload for name, payload in client.calls if name == "put_object"]
    assert put_calls
    for payload in put_calls:
        # no public ACL / grants are ever requested
        assert "ACL" not in payload
        assert "GrantFullControl" not in payload
        assert "GrantRead" not in payload


async def test_s3_storage_rejects_missing_or_incomplete_configuration():
    with pytest.raises(ServiceNotConfiguredError) as excinfo:
        S3Storage(bucket="")
    assert excinfo.value.status_code == 501

    with pytest.raises(ServiceNotConfiguredError):
        S3Storage(bucket="private-docs", access_key_id="AKIA-TEST")
    with pytest.raises(ServiceNotConfiguredError):
        S3Storage(bucket="private-docs", secret_access_key=S3_SECRET)


async def test_s3_storage_failures_do_not_leak_credentials():
    client = _FakeS3Client(
        fail_on="put_object",
        message=f"access denied key={S3_SECRET} endpoint=https://internal.example",
    )
    storage = S3Storage(
        bucket="private-docs",
        endpoint_url="https://internal.example",
        region="us-east-1",
        access_key_id="AKIA-TEST",
        secret_access_key=S3_SECRET,
        client=client,
    )

    with pytest.raises(StorageError) as excinfo:
        await storage.save(
            tenant_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            file_name="x.txt",
            content=b"x",
        )
    assert excinfo.value.status_code == 503
    assert S3_SECRET not in str(excinfo.value)
    assert "internal.example" not in str(excinfo.value)
    assert S3_SECRET not in repr(storage)

    head_failure = S3Storage(
        bucket="private-docs",
        client=_FakeS3Client(fail_on="head_object", message=S3_SECRET),
    )
    with pytest.raises(StorageError) as head_exc:
        await head_failure.exists("tenant/object.txt")
    assert S3_SECRET not in str(head_exc.value)


# ------------------------------------------------------------ configuration/factory
def test_storage_defaults_and_normalization():
    defaults = Settings(_env_file=None)
    assert defaults.storage_provider == "local"
    assert defaults.storage_bucket == ""

    settings = Settings(_env_file=None, storage_provider=" S3 ")
    assert settings.storage_provider == "s3"


@pytest.mark.parametrize("provider", ["ftp", "object-store", ""])
def test_invalid_storage_provider_is_rejected(provider):
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, storage_provider=provider)
    assert "STORAGE_PROVIDER must be local or s3" in str(excinfo.value)


def test_storage_credentials_are_not_in_settings_repr():
    settings = Settings(
        _env_file=None,
        storage_provider="s3",
        storage_bucket="private-docs",
        storage_access_key_id="AKIA-TEST",
        storage_secret_access_key=S3_SECRET,
    )
    rendered = repr(settings)
    assert S3_SECRET not in rendered
    assert "AKIA-TEST" not in rendered


def test_storage_factory_resolves_local_and_s3(tmp_path):
    local = get_storage(
        Settings(_env_file=None, storage_provider="local", storage_dir=str(tmp_path))
    )
    assert isinstance(local, LocalStorage)

    s3 = get_storage(
        Settings(
            _env_file=None,
            storage_provider="s3",
            storage_bucket="private-docs",
        )
    )
    assert isinstance(s3, S3Storage)

    unconfigured = build_storage(
        Settings(_env_file=None, storage_provider="s3", storage_bucket="")
    )
    assert isinstance(unconfigured, UnconfiguredStorage)


async def test_unconfigured_storage_fails_writes_but_delete_is_safe():
    storage = build_storage(
        Settings(_env_file=None, storage_provider="s3", storage_bucket="")
    )
    with pytest.raises(ServiceNotConfiguredError) as excinfo:
        await storage.save(
            tenant_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            file_name="x.txt",
            content=b"x",
        )
    assert excinfo.value.status_code == 501
    await storage.delete("anything")  # cleanup remains possible


# --------------------------------------------------------------- API roundtrip
async def test_upload_read_and_delete_use_local_storage(app, actor_factory):
    content = b"Private onboarding notes for the storage regression."
    client, session = await actor_factory(
        name="Ada", email="ada@example.com", org="Acme"
    )
    collection = await create_collection(client, session, name="Docs")

    response = await client.post(
        "/documents/upload",
        files={"file": ("notes.txt", content, "text/plain")},
        data={"collection_id": collection["id"], "classification": "internal"},
        headers=auth(session),
    )
    assert response.status_code == 201, response.text
    document_id = response.json()["id"]

    async with app.state.session_factory() as db:
        document = (
            await db.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
        ).scalar_one()
        storage_path = document.storage_path

    assert storage_path
    assert Path(storage_path).parent.name == session["user"]["organizationId"]
    assert await app.state.storage.exists(storage_path)
    assert await app.state.storage.read(storage_path) == content

    deleted = await client.delete(f"/documents/{document_id}", headers=auth(session))
    assert deleted.status_code == 204
    assert not await app.state.storage.exists(storage_path)


async def test_upload_with_incomplete_s3_config_returns_501(tmp_path):
    application = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            jwt_secret_key=TEST_JWT,
            database_url="sqlite+aiosqlite:///:memory:",
            qdrant_url=":memory:",
            storage_dir=str(tmp_path / "uploads"),
            storage_provider="s3",
            storage_bucket="",
        )
    )
    await create_all(application.state.engine)
    try:
        async with make_client(application) as client:
            session = await register(
                client, name="Ada", email="ada@example.com", org="Acme"
            )
            collection = await create_collection(client, session, name="Docs")
            response = await client.post(
                "/documents/upload",
                files={"file": ("notes.txt", b"private bytes", "text/plain")},
                data={"collection_id": collection["id"]},
                headers=auth(session),
            )
            assert response.status_code == 501
            assert response.json()["error"]["code"] == "SERVICE_NOT_CONFIGURED"
            assert S3_SECRET not in response.text

            listing = await client.get("/documents", headers=auth(session))
            assert listing.status_code == 200
            assert listing.json() == []
    finally:
        await drop_all(application.state.engine)
        await application.state.engine.dispose()


async def test_operational_storage_failure_does_not_break_ingestion(
    app, actor_factory, monkeypatch
):
    class FailingStorage:
        async def save(self, **kwargs):
            raise StorageError("storage unavailable")

        async def read(self, storage_path):
            raise NotImplementedError

        async def delete(self, storage_path):
            raise NotImplementedError

        async def exists(self, storage_path):
            raise NotImplementedError

    monkeypatch.setattr(app.state, "storage", FailingStorage())
    client, session = await actor_factory(
        name="Ada", email="ada@example.com", org="Acme"
    )
    collection = await create_collection(client, session, name="Docs")

    response = await client.post(
        "/documents/upload",
        files={"file": ("notes.txt", b"bytes still ingest from memory", "text/plain")},
        data={"collection_id": collection["id"]},
        headers=auth(session),
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "ready"
