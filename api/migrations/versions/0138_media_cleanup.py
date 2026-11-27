"""Media cleanup of posted videos (docs/decisions/2026-11-27-media-cleanup.md).

Adds `videos.keep_media` ("Giữ media"), `media_cleaned_at` and `media_freed_bytes`.

Revision ID: 0138
Revises: 0137
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0138"
down_revision = "0137"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("keep_media", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("videos", sa.Column("media_cleaned_at", sa.DateTime(timezone=True)))
    op.add_column("videos", sa.Column("media_freed_bytes", sa.BigInteger()))


def downgrade() -> None:
    op.drop_column("videos", "media_freed_bytes")
    op.drop_column("videos", "media_cleaned_at")
    op.drop_column("videos", "keep_media")
