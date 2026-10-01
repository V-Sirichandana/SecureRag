"""Authentication / session schemas."""

from __future__ import annotations

from pydantic import EmailStr, Field

from app.schemas.common import APIModel, RoleField, UTCDateTime


class RegisterIn(APIModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    # frontend sends organizationName
    organization_name: str = Field(min_length=1, max_length=200)


class LoginIn(APIModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    remember: bool = False


class RefreshIn(APIModel):
    refresh_token: str | None = None


class ForgotPasswordIn(APIModel):
    email: EmailStr


class AcceptInviteIn(APIModel):
    """Payload for POST /auth/accept-invite (sent from the invitation link)."""

    token: str = Field(min_length=20, max_length=4096)
    password: str = Field(min_length=8, max_length=128)


class SessionUser(APIModel):
    id: str
    name: str
    email: str
    role: RoleField
    department: str = "General"
    organization_id: str


class OrganizationOut(APIModel):
    id: str
    name: str
    plan: str
    member_count: int
    role: RoleField
    created_at: UTCDateTime


class SessionOut(APIModel):
    """Login/register/me payload: tokens + the frontend's AuthSession shape."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: SessionUser
    organizations: list[OrganizationOut]


class TokenOut(APIModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
