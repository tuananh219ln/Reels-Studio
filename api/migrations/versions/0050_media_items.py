"""The team's "Kho tư liệu": photos and clips uploaded by folder or downloaded from links, to use in scenes

Revision ID: 0050
Revises: 0049
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("folder", sa.String(length=200), server_default="", nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("seconds", sa.Float(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_media_items_created_by_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_media_items"),
    )
    op.create_index("ix_media_items_folder", "media_items", ["folder"])


def downgrade() -> None:
    op.drop_index("ix_media_items_folder", table_name="media_items")
    op.drop_table("media_items")
