"""video music and clone source

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only new nullable or defaulted columns: the previous api version keeps working during a deploy.
    op.add_column("videos", sa.Column("music_key", sa.String(length=200), nullable=True))
    op.add_column("videos", sa.Column("music_name", sa.String(length=200), nullable=True))
    op.add_column("videos", sa.Column("music_volume", sa.Integer(), server_default="25", nullable=False))
    op.add_column("videos", sa.Column("clone_source", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "clone_source")
    op.drop_column("videos", "music_volume")
    op.drop_column("videos", "music_name")
    op.drop_column("videos", "music_key")
