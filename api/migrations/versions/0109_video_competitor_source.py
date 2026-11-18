""" "Clone" from "Phân tích đối thủ": a video remembers the competitor's video it was built from (its Facebook link and
the channel's name, as text) and the row its sample comments are read from, which goes with the competitor.

Revision ID: 0109
Revises: 0108
Create Date: 2026-11-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("competitor_source_url", sa.Text(), nullable=True))
    op.add_column("videos", sa.Column("competitor_source_name", sa.String(200), nullable=True))
    op.add_column(
        "videos",
        sa.Column(
            "competitor_source_video_id",
            sa.Integer(),
            sa.ForeignKey("competitor_videos.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_videos_competitor_source_video_id", "videos", ["competitor_source_video_id"])


def downgrade() -> None:
    op.drop_index("ix_videos_competitor_source_video_id", table_name="videos")
    op.drop_column("videos", "competitor_source_video_id")
    op.drop_column("videos", "competitor_source_name")
    op.drop_column("videos", "competitor_source_url")
