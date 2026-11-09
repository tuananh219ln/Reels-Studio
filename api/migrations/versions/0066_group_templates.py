"""A topic group's own "Mẫu dựng" (several, one for its new videos) and the template a video wears

Revision ID: 0066
Revises: 0065
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_topic_templates",
        sa.Column(
            "knowledge_topic_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_topics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "edit_template_id", sa.Integer(), sa.ForeignKey("edit_templates.id", ondelete="CASCADE"), primary_key=True
        ),
    )
    # "app" or one of the group's own templates; null: the group puts none on its new videos.
    op.add_column("knowledge_topics", sa.Column("edit_template_default", postgresql.JSONB(), nullable=True))
    # The template last put on the video ({id, name, source, data}), so another one put on later replaces it.
    op.add_column("videos", sa.Column("edit_template", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "edit_template")
    op.drop_column("knowledge_topics", "edit_template_default")
    op.drop_table("knowledge_topic_templates")
