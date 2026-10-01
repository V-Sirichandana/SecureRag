"""Role-based access control within a single tenant."""

from __future__ import annotations

import pytest

from tests.conftest import auth, create_collection, create_document


@pytest.fixture
async def owner(actor_factory):
    return await actor_factory(name="Alice Owner", email="alice@example.com", org="Acme")


@pytest.fixture
async def member(owner, actor_factory):
    return await actor_factory(
        name="Mallory Member",
        email="mallory@example.com",
        role="member",
        invited_by=owner,
    )


@pytest.fixture
async def viewer(owner, actor_factory):
    return await actor_factory(
        name="Vera Viewer", email="vera@example.com", role="viewer", invited_by=owner
    )


async def test_member_can_view_audit(owner):
    client, session = owner
    response = await client.get("/audit", headers=auth(session))
    assert response.status_code == 200


async def test_member_cannot_view_audit(member):
    client, session = member
    response = await client.get("/audit", headers=auth(session))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


async def test_member_cannot_invite(member):
    client, session = member
    response = await client.post(
        "/users/invite",
        json={"email": "new@example.com", "role": "member", "department": "Sales"},
        headers=auth(session),
    )
    assert response.status_code == 403


async def test_member_cannot_create_api_keys(member):
    client, session = member
    response = await client.post(
        "/api-keys", json={"name": "key"}, headers=auth(session)
    )
    assert response.status_code == 403


async def test_member_cannot_change_settings(owner, member):
    client, session = member
    response = await client.put(
        "/settings/general",
        json={"organization_name": "Hijacked"},
        headers=auth(session),
    )
    assert response.status_code == 403


async def test_viewer_cannot_create_collections(viewer):
    client, session = viewer
    response = await client.post(
        "/collections", json={"name": "Docs"}, headers=auth(session)
    )
    assert response.status_code == 403  # manage_collections excludes viewer


async def test_member_can_upload_documents(owner, member):
    owner_client, owner_session = owner
    collection = await create_collection(owner_client, owner_session, name="Shared")

    member_client, member_session = member
    response = await member_client.post(
        "/documents",
        json={"name": "Member Upload.pdf", "collection_id": collection["id"]},
        headers=auth(member_session),
    )
    assert response.status_code == 201


async def test_member_cannot_delete_someone_elses_document(owner, member):
    owner_client, owner_session = owner
    collection = await create_collection(owner_client, owner_session)
    document = await create_document(
        owner_client, owner_session, collection_id=collection["id"]
    )

    member_client, member_session = member
    response = await member_client.delete(
        f"/documents/{document['id']}", headers=auth(member_session)
    )
    assert response.status_code == 403


async def test_owner_can_delete_any_document(owner, member):
    # collections need MANAGER+; the member only uploads into it
    owner_client, owner_session = owner
    collection = await create_collection(owner_client, owner_session, name="Shared")

    member_client, member_session = member
    document = await create_document(
        member_client, member_session, collection_id=collection["id"]
    )

    response = await owner_client.delete(
        f"/documents/{document['id']}", headers=auth(owner_session)
    )
    assert response.status_code == 204


async def test_member_cannot_promote_themselves(member):
    client, session = member
    response = await client.patch(
        f"/users/{session['user']['id']}",
        json={"role": "admin"},
        headers=auth(session),
    )
    assert response.status_code == 403


async def test_owner_can_promote_member(owner, member):
    owner_client, owner_session = owner
    _, member_session = member
    response = await owner_client.patch(
        f"/users/{member_session['user']['id']}",
        json={"role": "admin"},
        headers=auth(owner_session),
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


async def test_owner_cannot_modify_self(owner):
    client, session = owner
    response = await client.patch(
        f"/users/{session['user']['id']}",
        json={"status": "disabled"},
        headers=auth(session),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CANNOT_MODIFY_SELF"
