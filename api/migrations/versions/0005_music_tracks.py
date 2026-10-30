"""team music library

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "music_tracks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("topics", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("mood", sa.String(length=40), nullable=False),
        sa.Column("license_note", sa.Text(), server_default="", nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_music_tracks_created_by_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_music_tracks"),
    )


def downgrade() -> None:
    op.drop_table("music_tracks")
