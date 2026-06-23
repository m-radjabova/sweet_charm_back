"""add address coordinates

Revision ID: 0005_add_address_coordinates
Revises: 0004_add_user_avatar_file_id
Create Date: 2026-06-19 12:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_add_address_coordinates"
down_revision: str | None = "0004_add_user_avatar_file_id"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("addresses", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("addresses", sa.Column("longitude", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("addresses", "longitude")
    op.drop_column("addresses", "latitude")
