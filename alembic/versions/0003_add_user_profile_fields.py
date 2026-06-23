"""add user profile fields

Revision ID: 0003_add_user_profile_fields
Revises: 0002_add_gallery_images
Create Date: 2026-06-19 11:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_add_user_profile_fields"
down_revision: str | None = "0002_add_gallery_images"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("birthday", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "bio")
    op.drop_column("users", "birthday")
