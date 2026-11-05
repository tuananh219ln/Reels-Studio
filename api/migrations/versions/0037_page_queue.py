"""A Page's topic group and posting times, and its posting queue (page_queue_items)

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No group and no times for the Pages already there: their queue stays empty until a member sets them.
    op.add_column(
        "fanpages",
        sa.Column(
            "knowledge_topic_id", sa.Integer(), sa.ForeignKey("knowledge_topics.id", ondelete="SET NULL"), nullable=True
        ),
    )
    # "HH:MM" in Vietnam; null: the group's posting times.
    op.add_column("fanpages", sa.Column("post_times", JSONB(), nullable=True))
    op.create_table(
        "page_queue_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fanpage_id", sa.Integer(), sa.ForeignKey("fanpages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("auto_comment", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("added_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tried_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    # A video waits in one queue at a time.
    op.create_index("uq_page_queue_items_video_id", "page_queue_items", ["video_id"], unique=True)
    op.create_index("ix_page_queue_items_fanpage_id_position", "page_queue_items", ["fanpage_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_page_queue_items_fanpage_id_position", table_name="page_queue_items")
    op.drop_index("uq_page_queue_items_video_id", table_name="page_queue_items")
    op.drop_table("page_queue_items")
    op.drop_column("fanpages", "post_times")
    op.drop_column("fanpages", "knowledge_topic_id")
