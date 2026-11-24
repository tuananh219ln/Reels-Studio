"""Kho kiến thức "Tài liệu": the Markdown documents of a topic group (templates, plans, prompts, reports, the daily
job), read by assistants through MCP.

Revision ID: 0124
Revises: 0123
Create Date: 2026-11-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0124"
down_revision = "0123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topic_docs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "knowledge_topic_id", sa.Integer(), sa.ForeignKey("knowledge_topics.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("section", sa.String(20), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("knowledge_topic_id", "name", name="uq_topic_docs_topic_name"),
    )
    op.create_index("ix_topic_docs_knowledge_topic_id", "topic_docs", ["knowledge_topic_id"])


def downgrade() -> None:
    op.drop_index("ix_topic_docs_knowledge_topic_id", table_name="topic_docs")
    op.drop_table("topic_docs")
