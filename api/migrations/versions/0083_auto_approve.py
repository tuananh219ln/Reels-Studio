"""Tự duyệt: a switch on each member, and what it did with each video.

Revision ID: 0083
Revises: 0082
Create Date: 2026-11-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auto_approve", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "auto_approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("fanpage_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_auto_approvals_video_id", "auto_approvals", ["video_id"])
    op.create_index("ix_auto_approvals_user_id", "auto_approvals", ["user_id"])


def downgrade() -> None:
    op.drop_table("auto_approvals")
    op.drop_column("users", "auto_approve")
