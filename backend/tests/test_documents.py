"""Document CRUD, filters, visibility rules and pagination metadata."""

from __future__ import annotations

import pytest

from tests.conftest import auth, create_collection, create_document


@pytest.fixture
async def owner(actor_factory):
    return await actor_factory(name="Alice Owner", email="alice@example.com", org="Acme")


@pytest.fixture
async def member(owner, actor_factory):
    return await actor_factory(
        name="Mallory Member", email="mallory@example.com", role="member", invited_by=owner
    )


async def test_create_list_and_total_count(owner):
    client, session = owner
    collection = await create_collection(client, session)
    await create_document(client, session, collection_id=collection["id"])
    await create_document(
        client, session, collection_id=collection["id"], name="Notes.txt"
    )

    response = await client.get("/documents", headers=auth(session))
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.headers["x-total-count"] == "2"


async def test_search_filter(owner):
    client, session = owner
    collection = await create_collection(client, session)
    await create_document(
        client, session, collection_id=collection["id"], name="Annual Report.pdf"
    )
    await create_document(
        client, session, collection_id=collection["id"], name="Meeting Notes.txt"
    )

    response = await client.get(
        "/documents", params={"search": "annual"}, headers=auth(session)
    )
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Annual Report.pdf"]


async def test_classification_filter(owner):
    client, session = owner
    collection = await create_collection(client, session)
    await create_document(
        client,
        session,
        collection_id=collection["id"],
        name="Internal.pdf",
        classification="internal",
    )
    await create_document(
        client,
        session,
        collection_id=collection["id"],
        name="Secret.pdf",
        classification="confidential",
    )

    response = await client.get(
        "/documents", params={"classification": "confidential"}, headers=auth(session)
    )
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Secret.pdf"]


async def test_update_document(owner):
    client, session = owner
    collection = await create_collection(client, session)
    document = await create_document(
        client, session, collection_id=collection["id"]
    )

    response = await client.patch(
        f"/documents/{document['id']}",
        json={"name": "Renamed Report.pdf"},
        headers=auth(session),
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed Report.pdf"


async def test_delete_document(owner):
    client, session = owner
    collection = await create_collection(client, session)
    document = await create_document(
        client, session, collection_id=collection["id"]
    )

    deleted = await client.delete(
        f"/documents/{document['id']}", headers=auth(session)
    )
    assert deleted.status_code == 204

    fetched = await client.get(
        f"/documents/{document['id']}", headers=auth(session)
    )
    assert fetched.status_code == 404


async def test_internal_document_visible_org_wide(owner, member):
    """internal/public documents carry a global grant inside the tenant."""
    owner_client, owner_session = owner
    collection = await create_collection(owner_client, owner_session)
    document = await create_document(
        owner_client, owner_session, collection_id=collection["id"]
    )

    member_client, member_session = member
    response = await member_client.get(
        f"/documents/{document['id']}", headers=auth(member_session)
    )
    assert response.status_code == 200


async def test_confidential_document_hidden_from_other_members(owner, member):
    owner_client, owner_session = owner
    collection = await create_collection(owner_client, owner_session)
    document = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Board Pack.pdf",
        classification="confidential",
    )

    member_client, member_session = member
    response = await member_client.get(
        f"/documents/{document['id']}", headers=auth(member_session)
    )
    assert response.status_code == 404  # indistinguishable from missing

    listing = await member_client.get("/documents", headers=auth(member_session))
    assert all(item["id"] != document["id"] for item in listing.json())


async def test_pages_endpoint(owner):
    client, session = owner
    collection = await create_collection(client, session)
    document = await create_document(
        client, session, collection_id=collection["id"], name="Long Read.pdf"
    )

    response = await client.get(
        f"/documents/{document['id']}/pages", headers=auth(session)
    )
    assert response.status_code == 200
    pages = response.json()
    assert [page["pageNumber"] for page in pages] == [1, 2, 3]


async def test_update_permissions_grants_role_access(owner, member):
    owner_client, owner_session = owner
    collection = await create_collection(owner_client, owner_session)
    document = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Restricted Plan.pdf",
        classification="restricted",
    )

    # grant the MEMBER role read access
    granted = await owner_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "roles", "targets": ["member"]},
        headers=auth(owner_session),
    )
    assert granted.status_code == 200

    member_client, member_session = member
    response = await member_client.get(
        f"/documents/{document['id']}", headers=auth(member_session)
    )
    assert response.status_code == 200


async def test_member_cannot_manage_permissions(owner, member):
    owner_client, owner_session = owner
    collection = await create_collection(owner_client, owner_session)
    document = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        classification="confidential",
    )

    member_client, member_session = member
    response = await member_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "everyone"},
        headers=auth(member_session),
    )
    assert response.status_code in (403, 404)


async def test_missing_collection_is_404_on_create(owner):
    client, session = owner
    response = await client.post(
        "/documents",
        json={
            "name": "Orphan.pdf",
            "collection_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=auth(session),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "COLLECTION_NOT_FOUND"
