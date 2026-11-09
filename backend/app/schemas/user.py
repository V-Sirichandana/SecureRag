"""User schemas (frontend User contract)."""

from __future__ import annotations

from pydantic import Field, model_validator

from app.schemas.common import APIModel, RoleField, StatusLiteral, UTCDateTime


class UserOut(APIModel):
    id: str
    name: str
    email: str
    role: RoleField
    department: str = "General"
    status: StatusLiteral
    last_active: UTCDateTime
    created_at: UTCDateTime


class InviteUserIn(APIModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: RoleField
    department: str = Field(min_length=1, max_length=100)
    message: str | None = Field(default=None, max_length=2000)


class InviteUserOut(UserOut):
    """Invite response: the User contract plus the acceptance token.

    ``inviteToken`` is the stand-in for email delivery — it is only present
    outside production, where no mail provider is configured yet.
    """

    invite_token: str | None = None


class UpdateUserIn(APIModel):
    role: RoleField | None = None
    status: StatusLiteral | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> UpdateUserIn:
        if self.role is None and self.status is None:
            raise ValueError("Provide 'role' or 'status' to update.")
        return self
