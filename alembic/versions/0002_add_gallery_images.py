"""add gallery images table

Revision ID: 0002_add_gallery_images
Revises: 0001_initial_sweet_charm_schema
Create Date: 2026-06-18 18:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_add_gallery_images"
down_revision: str | None = "0001_initial_sweet_charm_schema"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gallery_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gallery_images_sort_order"), "gallery_images", ["sort_order"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_gallery_images_sort_order"), table_name="gallery_images")
    op.drop_table("gallery_images")
