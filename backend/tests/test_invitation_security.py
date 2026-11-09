"""Invitation integrity + user-management RBAC (M5.0).

C-1: an invitation must never deactivate or take over an account it did not
create, and its token must stay pinned to the inviting organization.
H-1/H-2: only owners may hand out or modify the owner role — with the role
read live from the database on every request.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app.models import Membership, User
from tests.conftest import PASSWORD, auth, make_client

TEST_SECRET = "test-secret-key-not-for-production"


@pytest.fixture
async def owner(actor_factory):
    return await actor_factory(name="Alice Owner", email="alice@example.com", org="Org A")


@pytest.fixture
async def outsider(actor_factory):
    return await actor_factory(name="Bob Outsider", email="bob@example.com", org="Org B")


@pytest.fixture
async def admin(owner, actor_factory):
    return await actor_factory(
        name="Ada Admin", email="ada@example.com", role="admin", invited_by=owner
    )


async def _user_row(app, email: str) -> User | None:
    async with app.state.session_factory() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()


async def _membership_role(app, user_id: str, tenant_id: str) -> str | None:
    async with app.state.session_factory() as session:
        result = await session.execute(
            select(Membership).where(
                Membership.user_id == uuid.UUID(user_id),
                Membership.tenant_id == uuid.UUID(tenant_id),
            )
        )
        row = result.scalar_one_or_none()
        return row.role.value if row else None


async def _invite(
    client, session: dict, *, email: str, role: str = "member"
) -> dict:
    response = await client.post(
        "/users/invite",
        json={"email": email, "role": role, "department": "Engineering"},
        headers=auth(session),
    )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- C-1
async def test_existing_account_survives_cross_tenant_invite(app, owner, outsider):
    """Inviting an existing account must not deactivate it nor hand over its
    password (the old flow did both: global lockout + account takeover)."""
    owner_client, owner_session = owner
    outsider_client, outsider_session = outsider
    victim_id = outsider_session["user"]["id"]
    victim_org = outsider_session["user"]["organizationId"]

    before = await _user_row(app, "bob@example.com")
    assert before is not None and before.is_active and before.status == "active"
    before_hash = before.password_hash

    invited = await _invite(owner_client, owner_session, email="bob@example.com")
    assert invited["inviteToken"]

    # the invite created the org-A membership but left the shared account alone
    row = await _user_row(app, "bob@example.com")
    assert row.is_active is True
    assert row.status == "active"
    assert row.password_hash == before_hash
    assert invited["status"] == "active"  # no longer pretends the account is pending

    # the account still works for its real organization
    me = await outsider_client.get("/auth/me", headers=auth(outsider_session))
    assert me.status_code == 200, me.text
    org_ids = [org["id"] for org in me.json()["organizations"]]
    assert victim_org in org_ids

    # attacker exchanges the invite token for their own password
    async with make_client(app) as attacker:
        accept = await attacker.post(
            "/auth/accept-invite",
            json={"token": invited["inviteToken"], "password": "attacker-pass-1"},
        )
    assert accept.status_code == 409
    assert accept.json()["error"]["code"] == "INVITE_ALREADY_ACCEPTED"

    # nothing about the victim's credentials changed
    row = await _user_row(app, "bob@example.com")
    assert row.password_hash == before_hash
    assert row.is_active is True
    assert row.status == "active"
    assert await _membership_role(app, victim_id, victim_org) == "OWNER"

    # the victim can still log in with their original password
    login = await outsider_client.post(
        "/auth/login", json={"email": "bob@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200, login.text


async def test_accept_invite_requires_live_membership(app, owner):
    """Removing the member revokes the invitation (token alone is not enough)."""
    owner_client, owner_session = owner
    invited = await _invite(owner_client, owner_session, email="carol@example.com")
    token = invited["inviteToken"]
    before_hash = (await _user_row(app, "carol@example.com")).password_hash

    removed = await owner_client.delete(
        f"/users/{invited['id']}", headers=auth(owner_session)
    )
    assert removed.status_code == 204, removed.text

    async with make_client(app) as invitee:
        accept = await invitee.post(
            "/auth/accept-invite", json={"token": token, "password": PASSWORD}
        )
    assert accept.status_code == 400
    assert accept.json()["error"]["code"] == "INVITE_INVALID"

    row = await _user_row(app, "carol@example.com")
    assert row.is_active is False
    assert row.password_hash == before_hash


async def test_invite_token_without_tenant_claim_is_rejected(app, owner):
    """Tokens issued before the organization scope existed cannot be replayed."""
    owner_client, owner_session = owner
    invited = await _invite(owner_client, owner_session, email="dave@example.com")

    now = datetime.now(UTC)
    legacy = jwt.encode(
        {
            "sub": invited["id"],
            "type": "invite",
            "jti": "legacy-test",
            "iat": now,
            "exp": now + timedelta(days=1),
        },
        TEST_SECRET,
        algorithm="HS256",
    )
    async with make_client(app) as invitee:
        accept = await invitee.post(
            "/auth/accept-invite", json={"token": legacy, "password": PASSWORD}
        )
    assert accept.status_code == 400
    assert accept.json()["error"]["code"] == "INVITE_INVALID"
    assert (await _user_row(app, "dave@example.com")).is_active is False


# --------------------------------------------------------------------------- H-1
async def test_admin_cannot_invite_owner_role(app, admin):
    admin_client, admin_session = admin
    response = await admin_client.post(
        "/users/invite",
        json={"email": "evil@example.com", "role": "owner", "department": "IT"},
        headers=auth(admin_session),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"
    # rejected before any write: no account was staged
    assert await _user_row(app, "evil@example.com") is None


async def test_owner_can_invite_owner_role(owner):
    owner_client, owner_session = owner
    invited = await _invite(
        owner_client, owner_session, email="coowner@example.com", role="owner"
    )
    assert invited["role"] == "owner"


async def test_admin_can_invite_member_role(admin):
    admin_client, admin_session = admin
    invited = await _invite(
        admin_client, admin_session, email="worker@example.com", role="member"
    )
    assert invited["role"] == "member"


# --------------------------------------------------------------------------- H-2
async def test_admin_cannot_change_owner_role(app, admin, owner):
    admin_client, admin_session = admin
    owner_client, owner_session = owner
    owner_id = owner_session["user"]["id"]
    owner_org = owner_session["user"]["organizationId"]

    response = await admin_client.patch(
        f"/users/{owner_id}",
        json={"role": "member"},
        headers=auth(admin_session),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"
    assert await _membership_role(app, owner_id, owner_org) == "OWNER"

    # direct fetch still reports the untouched role
    fetched = await owner_client.get(f"/users/{owner_id}", headers=auth(owner_session))
    assert fetched.status_code == 200
    assert fetched.json()["role"] == "owner"


async def test_admin_cannot_disable_owner(app, admin, owner):
    admin_client, admin_session = admin
    _, owner_session = owner
    owner_id = owner_session["user"]["id"]

    response = await admin_client.patch(
        f"/users/{owner_id}",
        json={"status": "disabled"},
        headers=auth(admin_session),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    row = await _user_row(app, "alice@example.com")
    assert row.is_active is True
    assert row.status == "active"


async def test_admin_cannot_remove_owner(app, admin, owner):
    admin_client, admin_session = admin
    owner_client, owner_session = owner
    owner_id = owner_session["user"]["id"]
    owner_org = owner_session["user"]["organizationId"]

    response = await admin_client.delete(f"/users/{owner_id}", headers=auth(admin_session))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"
    assert await _membership_role(app, owner_id, owner_org) == "OWNER"


async def test_owner_can_change_another_owners_role(owner, actor_factory):
    second_client, second_session = await actor_factory(
        name="Eve Owner", email="eve@example.com", role="owner", invited_by=owner
    )
    owner_client, owner_session = owner
    second_id = second_session["user"]["id"]

    response = await owner_client.patch(
        f"/users/{second_id}",
        json={"role": "admin"},
        headers=auth(owner_session),
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "admin"


async def test_owner_can_remove_another_owner(owner, actor_factory):
    _, second_session = await actor_factory(
        name="Eve Owner", email="eve@example.com", role="owner", invited_by=owner
    )
    owner_client, owner_session = owner
    second_id = second_session["user"]["id"]

    response = await owner_client.delete(f"/users/{second_id}", headers=auth(owner_session))
    assert response.status_code == 204, response.text

    members = await owner_client.get("/users", headers=auth(owner_session))
    assert members.status_code == 200
    assert second_id not in [member["id"] for member in members.json()]


# ----------------------------------------------------------- live role (step 11)
async def test_demoted_admin_loses_invite_access_live(owner, admin):
    admin_client, admin_session = admin
    owner_client, owner_session = owner
    admin_id = admin_session["user"]["id"]

    # works while the caller is an admin
    await _invite(admin_client, admin_session, email="first@example.com")

    demote = await owner_client.patch(
        f"/users/{admin_id}",
        json={"role": "member"},
        headers=auth(owner_session),
    )
    assert demote.status_code == 200, demote.text

    # next request reads the role from the database — no cached privilege
    response = await admin_client.post(
        "/users/invite",
        json={"email": "second@example.com", "role": "member", "department": "IT"},
        headers=auth(admin_session),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


async def test_promoted_owner_gains_owner_invite_live(owner, admin):
    admin_client, admin_session = admin
    owner_client, owner_session = owner
    admin_id = admin_session["user"]["id"]

    before = await admin_client.post(
        "/users/invite",
        json={"email": "early@example.com", "role": "owner", "department": "IT"},
        headers=auth(admin_session),
    )
    assert before.status_code == 403

    promote = await owner_client.patch(
        f"/users/{admin_id}",
        json={"role": "owner"},
        headers=auth(owner_session),
    )
    assert promote.status_code == 200, promote.text

    after = await admin_client.post(
        "/users/invite",
        json={"email": "late@example.com", "role": "owner", "department": "IT"},
        headers=auth(admin_session),
    )
    assert after.status_code == 201, after.text
    assert after.json()["role"] == "owner"
