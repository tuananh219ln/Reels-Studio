"""Who made a topic group and a plan idea, so only they delete it (part 4 of per-user-settings-ownership)

Revision ID: 0068
Revises: 0067
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_topics", sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True)
    )
    op.add_column(
        "topic_plan_items", sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True)
    )
    # The maker was never kept: the member who last changed it, as for the Pages' owners (2026-11-03), else the one
    # who made its first video. A group still without one is deleted by nobody.
    op.execute("UPDATE knowledge_topics SET created_by_id = updated_by_id")
    op.execute(
        """
        UPDATE knowledge_topics SET created_by_id = (
            SELECT videos.created_by_id FROM videos
            WHERE videos.knowledge_topic_id = knowledge_topics.id ORDER BY videos.id LIMIT 1
        )
        WHERE created_by_id IS NULL
        """
    )
    # An idea: whoever last changed it, else its group's maker.
    op.execute(
        """
        UPDATE topic_plan_items SET created_by_id = COALESCE(
            updated_by_id,
            (SELECT created_by_id FROM knowledge_topics WHERE knowledge_topics.id = topic_plan_items.knowledge_topic_id)
        )
        """
    )


def downgrade() -> None:
    op.drop_column("topic_plan_items", "created_by_id")
    op.drop_column("knowledge_topics", "created_by_id")
