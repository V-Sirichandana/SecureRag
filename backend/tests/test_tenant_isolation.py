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


async def test_foreign_tenant_cannot_mutate_document(doc_a, doc_b):
    client_a, session_a, document_a = doc_a
    client_b, session_b, _ = doc_b
    headers_b = auth(session_b)
    document_id = document_a["id"]

    pages = await client_b.get(
        f"/documents/{document_id}/pages", headers=headers_b
    )
    assert pages.status_code == 404
    assert pages.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"

    updated = await client_b.patch(
        f"/documents/{document_id}",
        json={"name": "Hijacked.pdf"},
        headers=headers_b,
    )
    assert updated.status_code == 404
    assert updated.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"

    permissions = await client_b.put(
        f"/documents/{document_id}/permissions",
        json={"scope": "everyone", "targets": []},
        headers=headers_b,
    )
    assert permissions.status_code == 404
    assert permissions.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"

    content = await client_b.post(
        f"/documents/{document_id}/content",
        files={"file": ("hijack.txt", b"overwrite", "text/plain")},
        headers=headers_b,
    )
    assert content.status_code == 404
    assert content.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"

    deleted = await client_b.delete(
        f"/documents/{document_id}", headers=headers_b
    )
    assert deleted.status_code == 404
    assert deleted.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"

    own = await client_a.get(
        f"/documents/{document_id}", headers=auth(session_a)
    )
    assert own.status_code == 200
    assert own.json()["name"] == "Acme Secret.pdf"
    assert own.json()["collectionId"] == document_a["collectionId"]


async def test_foreign_tenant_cannot_mutate_collection(user_a, user_b):
    client_a, session_a = user_a
    collection_a = await create_collection(client_a, session_a, name="Acme Files")

    client_b, session_b = user_b
    headers_b = auth(session_b)
    collection_id = collection_a["id"]

    updated = await client_b.patch(
        f"/collections/{collection_id}",
        json={"name": "Hijacked"},
        headers=headers_b,
    )
    assert updated.status_code == 404
    assert updated.json()["error"]["code"] == "COLLECTION_NOT_FOUND"

    deleted = await client_b.delete(
        f"/collections/{collection_id}", headers=headers_b
    )
    assert deleted.status_code == 404
    assert deleted.json()["error"]["code"] == "COLLECTION_NOT_FOUND"

    own = await client_a.get(
        f"/collections/{collection_id}", headers=auth(session_a)
    )
    assert own.status_code == 200
    assert own.json()["name"] == "Acme Files"


async def test_foreign_collection_cannot_be_used_by_documents_or_chat(user_a, user_b):
    client_a, session_a = user_a
    collection_a = await create_collection(client_a, session_a, name="Acme Files")
    document_a = await create_document(
        client_a, session_a, collection_id=collection_a["id"], name="Acme Notes.pdf"
    )

    client_b, session_b = user_b
    collection_b = await create_collection(client_b, session_b, name="Globex Files")
    headers_a = auth(session_a)

    created = await client_a.post(
        "/documents",
        json={"name": "Cross Tenant.pdf", "collectionId": collection_b["id"]},
        headers=headers_a,
    )
    assert created.status_code == 404
    assert created.json()["error"]["code"] == "COLLECTION_NOT_FOUND"

    moved = await client_a.patch(
        f"/documents/{document_a['id']}",
        json={"collectionId": collection_b["id"]},
        headers=headers_a,
    )
    assert moved.status_code == 404
    assert moved.json()["error"]["code"] == "COLLECTION_NOT_FOUND"

    conversation = await client_a.post(
        "/chat/conversations",
        json={"title": "Foreign collection", "collectionId": collection_b["id"]},
        headers=headers_a,
    )
    assert conversation.status_code == 404
    assert conversation.json()["error"]["code"] == "COLLECTION_NOT_FOUND"

    filtered = await client_a.get(
        f"/documents?collectionId={collection_b['id']}", headers=headers_a
    )
    assert filtered.status_code == 200
    assert filtered.json() == []
    assert filtered.headers["X-Total-Count"] == "0"

    unchanged = await client_a.get(
        f"/documents/{document_a['id']}", headers=headers_a
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["collectionId"] == collection_a["id"]


async def test_conversation_mutations_and_feedback_are_isolated(user_a, user_b):
    client_b, session_b = user_b
    created = await client_b.post(
        "/chat/conversations",
        json={"title": "Bob private chat"},
        headers=auth(session_b),
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    message = await client_b.post(
        f"/chat/conversations/{conversation_id}/messages",
        json={"role": "assistant", "content": "Bob private answer"},
        headers=auth(session_b),
    )
    assert message.status_code == 201
    message_id = message.json()["id"]

    client_a, session_a = user_a
    headers_a = auth(session_a)

    deleted = await client_a.delete(
        f"/chat/conversations/{conversation_id}", headers=headers_a
    )
    assert deleted.status_code == 404
    assert deleted.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    posted = await client_a.post(
        f"/chat/conversations/{conversation_id}/messages",
        json={"role": "assistant", "content": "Injected message"},
        headers=headers_a,
    )
    assert posted.status_code == 404
    assert posted.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    feedback = await client_a.post(
        f"/chat/messages/{message_id}/feedback",
        json={"feedback": "down"},
        headers=headers_a,
    )
    assert feedback.status_code == 404
    assert feedback.json()["error"]["code"] == "MESSAGE_NOT_FOUND"

    own = await client_b.get(
        f"/chat/conversations/{conversation_id}", headers=auth(session_b)
    )
    assert own.status_code == 200
    assert own.json()["messageCount"] == 1
    assert own.json()["messages"][0]["id"] == message_id
    assert own.json()["messages"][0]["feedback"] is None


async def test_identity_fields_are_ignored_on_create_and_list(user_a, user_b):
    client_a, session_a = user_a
    client_b, session_b = user_b
    tenant_b = session_b["user"]["organizationId"]
    user_b_id = session_b["user"]["id"]
    headers_a = auth(session_a)
    headers_b = auth(session_b)

    collection_b = await create_collection(client_b, session_b, name="Globex Files")
    document_b = await create_document(
        client_b, session_b, collection_id=collection_b["id"], name="Globex Notes.pdf"
    )

    collection = await client_a.post(
        "/collections",
        json={
            "name": "Injected Collection",
            "tenant_id": tenant_b,
            "tenantId": tenant_b,
        },
        headers=headers_a,
    )
    assert collection.status_code == 201
    collection_id = collection.json()["id"]
    foreign_collection = await client_b.get(
        f"/collections/{collection_id}", headers=headers_b
    )
    assert foreign_collection.status_code == 404
    assert (
        await client_a.get(f"/collections/{collection_id}", headers=headers_a)
    ).status_code == 200

    document = await client_a.post(
        "/documents",
        json={
            "name": "Injected Document.pdf",
            "collectionId": collection_id,
            "tenant_id": tenant_b,
            "tenantId": tenant_b,
            "created_by": user_b_id,
            "createdBy": user_b_id,
        },
        headers=headers_a,
    )
    assert document.status_code == 201
    document_id = document.json()["id"]
    assert document.json()["owner"] == "Alice Owner"
    assert (
        await client_b.get(f"/documents/{document_id}", headers=headers_b)
    ).status_code == 404

    listing_a = await client_a.get(
        f"/documents?tenantId={tenant_b}", headers=headers_a
    )
    assert listing_a.status_code == 200
    ids_a = {item["id"] for item in listing_a.json()}
    assert document_id in ids_a
    assert document_b["id"] not in ids_a

    listing_b = await client_b.get(
        f"/documents?tenantId={session_a['user']['organizationId']}", headers=headers_b
    )
    assert listing_b.status_code == 200
    ids_b = {item["id"] for item in listing_b.json()}
    assert document_b["id"] in ids_b
    assert document_id not in ids_b

    hinted = await client_a.get(
        "/documents",
        headers={**headers_a, "X-Tenant-Id": tenant_b},
    )
    assert hinted.status_code == 403
    assert hinted.json()["error"]["code"] == "TENANT_ACCESS_DENIED"

    search = await client_a.get(
        "/search",
        params={"q": "Globex", "tenantId": tenant_b, "tenant_id": tenant_b},
        headers=headers_a,
    )
    assert search.status_code == 200
    assert all(hit["id"] != document_b["id"] for hit in search.json())

    conversation = await client_a.post(
        "/chat/conversations",
        json={
            "title": "Injected Chat",
            "tenant_id": tenant_b,
            "tenantId": tenant_b,
            "user_id": user_b_id,
            "userId": user_b_id,
        },
        headers=headers_a,
    )
    assert conversation.status_code == 201
    conversation_id = conversation.json()["id"]
    assert (
        await client_b.get(
            f"/chat/conversations/{conversation_id}", headers=headers_b
        )
    ).status_code == 404
    assert (
        await client_a.get(
            f"/chat/conversations/{conversation_id}", headers=headers_a
        )
    ).status_code == 200
