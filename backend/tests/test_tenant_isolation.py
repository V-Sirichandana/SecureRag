"""Cross-tenant isolation — the invariant SecureRAG must never violate.

User A (Tenant A) and User B (Tenant B) must never see each other's resources.
A missing resource and a foreign resource are indistinguishable (both 404).
"""

from __future__ import annotations

import pytest

from tests.conftest import auth, create_collection, create_document


@pytest.fixture
async def user_a(actor_factory):
    return await actor_factory(
        name="Alice Owner", email="alice@example.com", org="Acme Corp"
    )


@pytest.fixture
async def user_b(actor_factory):
    return await actor_factory(
        name="Bob Owner", email="bob@example.org", org="Globex Inc"
    )


@pytest.fixture
async def doc_a(user_a):
    client, session = user_a
    collection = await create_collection(client, session, name="Acme Files")
    document = await create_document(
        client, session, collection_id=collection["id"], name="Acme Secret.pdf"
    )
    return client, session, document


@pytest.fixture
async def doc_b(user_b):
    client, session = user_b
    collection = await create_collection(client, session, name="Globex Files")
    document = await create_document(
        client, session, collection_id=collection["id"], name="Globex Secret.pdf"
    )
    return client, session, document


async def test_user_a_reads_own_document(doc_a):
    client, session, document = doc_a
    response = await client.get(
        f"/documents/{document['id']}", headers=auth(session)
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Acme Secret.pdf"


async def test_user_b_reads_own_document(doc_b):
    client, session, document = doc_b
    response = await client.get(
        f"/documents/{document['id']}", headers=auth(session)
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Globex Secret.pdf"


async def test_user_a_cannot_read_user_b_document(doc_a, doc_b):
    client_a, session_a, _ = doc_a
    _, _, document_b = doc_b
    response = await client_a.get(
        f"/documents/{document_b['id']}", headers=auth(session_a)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


async def test_user_b_cannot_read_user_a_document(doc_a, doc_b):
    client_b, session_b, _ = doc_b
    _, _, document_a = doc_a
    response = await client_b.get(
        f"/documents/{document_a['id']}", headers=auth(session_b)
    )
    assert response.status_code == 404


async def test_document_lists_are_disjoint(doc_a, doc_b):
    client_a, session_a, document_a = doc_a
    client_b, session_b, document_b = doc_b

    list_a = await client_a.get("/documents", headers=auth(session_a))
    list_b = await client_b.get("/documents", headers=auth(session_b))
    assert list_a.status_code == 200 and list_b.status_code == 200

    ids_a = {item["id"] for item in list_a.json()}
    ids_b = {item["id"] for item in list_b.json()}
    assert document_a["id"] in ids_a
    assert document_b["id"] in ids_b
    assert ids_a.isdisjoint(ids_b)


async def test_collection_is_isolated(user_a, user_b):
    client_b, session_b = user_b
    collection_b = await create_collection(client_b, session_b, name="Private")

    client_a, session_a = user_a
    response = await client_a.get(
        f"/collections/{collection_b['id']}", headers=auth(session_a)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COLLECTION_NOT_FOUND"

    list_a = await client_a.get("/collections", headers=auth(session_a))
    assert all(item["id"] != collection_b["id"] for item in list_a.json())


async def test_user_directory_is_isolated(user_a, user_b):
    client_a, session_a = user_a
    response = await client_a.get("/users", headers=auth(session_a))
    assert response.status_code == 200
    emails = {item["email"] for item in response.json()}
    assert emails == {"alice@example.com"}


async def test_foreign_tenant_hint_is_rejected(user_a, user_b):
    """Even an explicit X-Tenant-Id cannot cross the membership boundary."""
    _, session_b = user_b
    client_a, session_a = user_a
    response = await client_a.get(
        "/users",
        headers={
            **auth(session_a),
            "X-Tenant-Id": session_b["user"]["organizationId"],
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TENANT_ACCESS_DENIED"


async def test_audit_trail_is_isolated(doc_a, user_b):
    client_a, session_a, _ = doc_a
    client_b, session_b = user_b
    # generate an auditable action in tenant B
    await create_collection(client_b, session_b, name="Bob's Audit Breadcrumb")

    response = await client_a.get("/audit", headers=auth(session_a))
    assert response.status_code == 200
    labels = [event["resource"] for event in response.json()]
    assert not any("Bob" in label for label in labels)


async def test_conversations_are_isolated(user_a, user_b):
    client_b, session_b = user_b
    created = await client_b.post(
        "/chat/conversations",
        json={"title": "Bob private chat"},
        headers=auth(session_b),
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    client_a, session_a = user_a
    listing = await client_a.get(
        "/chat/conversations", headers=auth(session_a)
    )
    assert listing.status_code == 200
    assert all(item["id"] != conversation_id for item in listing.json())

    fetched = await client_a.get(
        f"/chat/conversations/{conversation_id}", headers=auth(session_a)
    )
    assert fetched.status_code == 404


async def test_api_keys_are_isolated(user_a, user_b):
    client_b, session_b = user_b
    created = await client_b.post(
        "/api-keys",
        json={"name": "Bob key", "environment": "test"},
        headers=auth(session_b),
    )
    assert created.status_code == 201
    key_id = created.json()["key"]["id"]

    client_a, session_a = user_a
    listing = await client_a.get("/api-keys", headers=auth(session_a))
    assert listing.status_code == 200
    assert all(item["id"] != key_id for item in listing.json())

    revoked = await client_a.delete(
        f"/api-keys/{key_id}", headers=auth(session_a)
    )
    assert revoked.status_code == 404
