"""A video made from a finished MP4 (mode "upload"): the file, what ffprobe read, a note and an idempotency key.

Revision ID: 0130
Revises: 0129
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0130"
down_revision = "0129"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("source_mp4", postgresql.JSONB()))
    op.add_column("videos", sa.Column("media_info", postgresql.JSONB()))
    op.add_column("videos", sa.Column("upload_note", sa.Text()))
    op.add_column("videos", sa.Column("upload_key", sa.String(100)))
    op.create_index("ix_videos_upload_key", "videos", ["upload_key"])


def downgrade() -> None:
    op.drop_index("ix_videos_upload_key", table_name="videos")
    op.drop_column("videos", "upload_key")
    op.drop_column("videos", "upload_note")
    op.drop_column("videos", "media_info")
    op.drop_column("videos", "source_mp4")
