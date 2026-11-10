"""A topic group's "Chữ & phụ đề": its own text look, the AI's pick for each video, and the AI's suggested looks
(2026-11-10)

Revision ID: 0074
Revises: 0073
Create Date: 2026-11-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No group has a look of its own yet: their videos keep taking their maker's, as before.
    op.add_column("knowledge_topics", sa.Column("text_look", postgresql.JSONB(), nullable=True))
    op.add_column("knowledge_topics", sa.Column("text_ai", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("knowledge_topics", sa.Column("text_suggestions", postgresql.JSONB(), nullable=True))
    # One "AI gợi ý" at a time per group, as for its plan.
    op.create_index(
        "uq_jobs_active_text_look",
        "jobs",
        ["knowledge_topic_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running') AND kind = 'text_look'"),
    )


def downgrade() -> None:
    op.drop_index("uq_jobs_active_text_look", table_name="jobs")
    op.drop_column("knowledge_topics", "text_suggestions")
    op.drop_column("knowledge_topics", "text_ai")
    op.drop_column("knowledge_topics", "text_look")
