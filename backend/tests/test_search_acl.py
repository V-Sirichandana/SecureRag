"""M5.1 security regression: GET /search applies the retrieval ACL.

The global search endpoint must surface only documents the caller is allowed
to view — the SAME ``DocumentRepository.visibility_clause`` predicate behind
retrieval — while collections (including their document counts) stay
tenant-scoped and permission-aware.
"""

from __future__ import annotations

import pytest

from tests.conftest import auth, create_collection, create_document


@pytest.fixture
async def owner(actor_factory):
    return await actor_factory(name="Olivia Owner", email="olivia@acme.com", org="Acme Corp")


@pytest.fixture
async def member(owner, actor_factory):
    return await actor_factory(
        name="Mia Member", email="mia@acme.com", role="member", invited_by=owner
    )


async def search(client, session, *, q: str, headers: dict | None = None):
    return await client.get(
        "/search", params={"q": q}, headers={**auth(session), **(headers or {})}
    )


def document_hits(response) -> list[dict]:
    assert response.status_code == 200, response.text
    return [item for item in response.json() if item["type"] == "document"]


def collection_hits(response) -> list[dict]:
    assert response.status_code == 200, response.text
    return [item for item in response.json() if item["type"] == "collection"]


# ------------------------------------------- A. member visibility rules
async def test_member_sees_own_document(owner, member):
    owner_client, owner_session = owner
    member_client, member_session = member
    collection = await create_collection(owner_client, owner_session, name="Notes")
    document = await create_document(
        member_client,
        member_session,
        collection_id=collection["id"],
        name="Quokka Personal Notes.pdf",
        classification="confidential",
    )

    hits = document_hits(await search(member_client, member_session, q="Quokka"))
    assert document["id"] in {hit["id"] for hit in hits}


async def test_member_sees_document_via_user_grant(owner, member):
    owner_client, owner_session = owner
    member_client, member_session = member
    member_id = member_session["user"]["id"]
    collection = await create_collection(owner_client, owner_session, name="Board")
    document = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Quokka Board Dossier.pdf",
        classification="confidential",
    )

    hits = document_hits(await search(member_client, member_session, q="Quokka"))
    assert document["id"] not in {hit["id"] for hit in hits}

    granted = await owner_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "users", "targets": [member_id]},
        headers=auth(owner_session),
    )
    assert granted.status_code == 200, granted.text

    hits = document_hits(await search(member_client, member_session, q="Quokka"))
    assert document["id"] in {hit["id"] for hit in hits}


async def test_member_sees_document_via_role_grant(owner, member):
    owner_client, owner_session = owner
    member_client, member_session = member
    collection = await create_collection(owner_client, owner_session, name="Board")
    document = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Quokka Restricted Brief.pdf",
        classification="restricted",
    )

    hits = document_hits(await search(member_client, member_session, q="Quokka"))
    assert document["id"] not in {hit["id"] for hit in hits}

    granted = await owner_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "roles", "targets": ["member"]},
        headers=auth(owner_session),
    )
    assert granted.status_code == 200, granted.text

    hits = document_hits(await search(member_client, member_session, q="Quokka"))
    assert document["id"] in {hit["id"] for hit in hits}


async def test_member_sees_org_wide_document(owner, member):
    owner_client, owner_session = owner
    member_client, member_session = member
    collection = await create_collection(owner_client, owner_session, name="Docs")
    document = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Quokka Field Guide.pdf",
        classification="internal",
    )

    hits = document_hits(await search(member_client, member_session, q="Quokka"))
    assert document["id"] in {hit["id"] for hit in hits}


# ------------------------------------- B. confidential stays undiscoverable
async def test_member_cannot_discover_confidential_document(owner, member):
    owner_client, owner_session = owner
    member_client, member_session = member
    collection = await create_collection(owner_client, owner_session, name="Quokka Vault")
    confidential = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Quokka Confidential Dossier.pdf",
        classification="confidential",
    )
    internal = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Quokka Field Guide.pdf",
        classification="internal",
    )

    response = await search(member_client, member_session, q="Quokka")
    hits = {hit["id"] for hit in document_hits(response)}
    assert internal["id"] in hits
    assert confidential["id"] not in hits

    collections = collection_hits(response)
    vault = next(item for item in collections if item["title"] == "Quokka Vault")
    # the confidential document must not leak through the member-visible count
    assert vault["subtitle"] == "1 documents"


# ------------------------------------------------------- C. tenant isolation
async def test_search_is_tenant_scoped(actor_factory):
    owner_a, session_a = await actor_factory(
        name="Alice Owner", email="alice@example.com", org="Acme Corp"
    )
    owner_b, session_b = await actor_factory(
        name="Bob Owner", email="bob@example.org", org="Globex Inc"
    )
    collection_a = await create_collection(owner_a, session_a, name="Acme Files")
    collection_b = await create_collection(owner_b, session_b, name="Globex Files")
    document_a = await create_document(
        owner_a,
        session_a,
        collection_id=collection_a["id"],
        name="Nabisco Merger Brief.pdf",
    )
    document_b = await create_document(
        owner_b,
        session_b,
        collection_id=collection_b["id"],
        name="Nabisco Merger Brief.pdf",
    )

    hits = {hit["id"] for hit in document_hits(await search(owner_b, session_b, q="Nabisco"))}
    assert document_b["id"] in hits
    assert document_a["id"] not in hits


# ------------------------------------------- D. admin sees confidential docs
async def test_admin_sees_confidential_document(owner, member, actor_factory):
    owner_client, owner_session = owner
    member_client, member_session = member
    admin_client, admin_session = await actor_factory(
        name="Ana Admin",
        email="ana@acme.com",
        role="admin",
        invited_by=(owner_client, owner_session),
    )
    collection = await create_collection(owner_client, owner_session, name="Board")
    confidential = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Marmot Board Dossier.pdf",
        classification="confidential",
    )

    member_hits = {
        hit["id"]
        for hit in document_hits(
            await search(member_client, member_session, q="Marmot")
        )
    }
    assert confidential["id"] not in member_hits

    admin_hits = {
        hit["id"]
        for hit in document_hits(
            await search(admin_client, admin_session, q="Marmot")
        )
    }
    assert confidential["id"] in admin_hits


# --------------------------------------- E. owner keeps tenant-wide visibility
async def test_owner_sees_confidential_document(owner, member):
    owner_client, owner_session = owner
    member_client, member_session = member
    collection = await create_collection(owner_client, owner_session, name="Board")
    confidential = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Numbat Board Dossier.pdf",
        classification="confidential",
    )

    owner_hits = {
        hit["id"]
        for hit in document_hits(
            await search(owner_client, owner_session, q="Numbat")
        )
    }
    assert confidential["id"] in owner_hits

    member_hits = {
        hit["id"]
        for hit in document_hits(
            await search(member_client, member_session, q="Numbat")
        )
    }
    assert confidential["id"] not in member_hits


# ----------------------------------------------------------- F. auth required
async def test_search_requires_authentication(client):
    response = await client.get("/search", params={"q": "anything"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_foreign_tenant_hint_is_rejected(actor_factory):
    owner_a, session_a = await actor_factory(
        name="Alice Owner", email="alice@example.com", org="Acme Corp"
    )
    _, session_b = await actor_factory(
        name="Bob Owner", email="bob@example.org", org="Globex Inc"
    )

    response = await owner_a.get(
        "/search",
        params={"q": "anything"},
        headers={**auth(session_a), "X-Tenant-Id": session_b["user"]["organizationId"]},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TENANT_ACCESS_DENIED"


# -------------------------------- G. grant/revoke applies with no re-ingestion
async def test_permission_grant_appears_without_reingestion(owner, member):
    owner_client, owner_session = owner
    member_client, member_session = member
    member_id = member_session["user"]["id"]
    collection = await create_collection(owner_client, owner_session, name="Runtime")
    document = await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Runtime Grant Dossier.pdf",
        classification="confidential",
    )

    before = document_hits(await search(member_client, member_session, q="Runtime Grant"))
    assert document["id"] not in {hit["id"] for hit in before}

    granted = await owner_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "users", "targets": [member_id]},
        headers=auth(owner_session),
    )
    assert granted.status_code == 200, granted.text

    during = document_hits(await search(member_client, member_session, q="Runtime Grant"))
    assert document["id"] in {hit["id"] for hit in during}

    revoked = await owner_client.put(
        f"/documents/{document['id']}/permissions",
        json={"scope": "users", "targets": []},
        headers=auth(owner_session),
    )
    assert revoked.status_code == 200, revoked.text

    after = document_hits(await search(member_client, member_session, q="Runtime Grant"))
    assert document["id"] not in {hit["id"] for hit in after}


# --------------------------------------- H. collection counts stay permissioned
async def test_collection_counts_respect_visibility(owner, member, actor_factory):
    owner_client, owner_session = owner
    member_client, member_session = member
    admin_client, admin_session = await actor_factory(
        name="Ana Admin",
        email="ana@acme.com",
        role="admin",
        invited_by=(owner_client, owner_session),
    )
    collection = await create_collection(owner_client, owner_session, name="Zephyr Archive")
    await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Zephyr Confidential Dossier.pdf",
        classification="confidential",
    )
    await create_document(
        owner_client,
        owner_session,
        collection_id=collection["id"],
        name="Zephyr Field Guide.pdf",
        classification="internal",
    )

    member_response = await search(member_client, member_session, q="Zephyr")
    member_vault = next(
        item for item in collection_hits(member_response) if item["title"] == "Zephyr Archive"
    )
    assert member_vault["subtitle"] == "1 documents"

    admin_response = await search(admin_client, admin_session, q="Zephyr")
    admin_vault = next(
        item for item in collection_hits(admin_response) if item["title"] == "Zephyr Archive"
    )
    assert admin_vault["subtitle"] == "2 documents"
