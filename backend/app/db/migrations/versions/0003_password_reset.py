"""password reset token storage on users

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-04 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("password_reset_token_hash", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("password_reset_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_users_password_reset_token_hash", ["password_reset_token_hash"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_password_reset_token_hash")
        batch_op.drop_column("password_reset_expires_at")
        batch_op.drop_column("password_reset_token_hash")
