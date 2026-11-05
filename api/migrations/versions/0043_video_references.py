"""video_references: a sample video members learn from ("Từ video mẫu"); videos.reference_id and reference_mode;
knowledge_topics.learn_prompt and analyze_prompt

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_references",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_name", sa.String(300), nullable=False),
        sa.Column("video_key", sa.String(200), nullable=True),
        sa.Column("seconds", sa.Float(), nullable=True),
        sa.Column("transcript", sa.Text(), server_default="", nullable=False),
        sa.Column("frames", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("analysis", sa.Text(), server_default="", nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "videos",
        sa.Column(
            "reference_id", sa.Integer(), sa.ForeignKey("video_references.id", ondelete="SET NULL"), nullable=True
        ),
    )
    op.add_column("videos", sa.Column("reference_mode", sa.String(16), nullable=True))
    op.create_index("ix_videos_reference_id", "videos", ["reference_id"])
    # Empty for every group already there: the default prompts in prompts/ are used until a member writes one.
    op.add_column("knowledge_topics", sa.Column("learn_prompt", sa.Text(), server_default="", nullable=False))
    op.add_column("knowledge_topics", sa.Column("analyze_prompt", sa.Text(), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("knowledge_topics", "analyze_prompt")
    op.drop_column("knowledge_topics", "learn_prompt")
    op.drop_index("ix_videos_reference_id", table_name="videos")
    op.drop_column("videos", "reference_mode")
    op.drop_column("videos", "reference_id")
    op.drop_table("video_references")
