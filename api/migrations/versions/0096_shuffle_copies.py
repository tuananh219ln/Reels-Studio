"""'Nhân bản xáo cảnh': a copy keeps the video it was shuffled from, its scene order, and the title to change.

Revision ID: 0096
Revises: 0095
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "videos",
        sa.Column("shuffled_from_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_videos_shuffled_from_id", "videos", ["shuffled_from_id"])
    op.add_column("videos", sa.Column("scene_order", sa.Text(), nullable=True))
    op.add_column("videos", sa.Column("review_title", sa.Text(), nullable=True))
    op.add_column("scenes", sa.Column("source_scene_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("scenes", "source_scene_id")
    op.drop_column("videos", "review_title")
    op.drop_column("videos", "scene_order")
    op.drop_index("ix_videos_shuffled_from_id", table_name="videos")
    op.drop_column("videos", "shuffled_from_id")
