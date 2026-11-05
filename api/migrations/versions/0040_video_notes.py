"""video_notes and knowledge_topics.revise_prompt: comments at a second of the video, sent to the AI to fix

Revision ID: 0040
Revises: 0039
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("at", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(8), nullable=False, server_default="open"),
        sa.Column("reply", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_video_notes_video_id", "video_notes", ["video_id"])
    # Empty for every group: "Nhờ AI sửa" uses the default prompt until a member writes one.
    op.add_column("knowledge_topics", sa.Column("revise_prompt", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("knowledge_topics", "revise_prompt")
    op.drop_index("ix_video_notes_video_id", table_name="video_notes")
    op.drop_table("video_notes")
