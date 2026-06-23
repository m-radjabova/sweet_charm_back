"""add user avatar file id

Revision ID: 0004_add_user_avatar_file_id
Revises: 0003_add_user_profile_fields
Create Date: 2026-06-19 11:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_add_user_avatar_file_id"
down_revision: str | None = "0003_add_user_profile_fields"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_file_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_file_id")
