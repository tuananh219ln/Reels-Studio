"""Who has a video open: one row per open page, refreshed every few seconds and deleted once it falls silent

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_presence",
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("tab", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("editing", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["video_id"], ["videos.id"], name="fk_video_presence_video_id_videos", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_video_presence_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("video_id", "tab", name="pk_video_presence"),
    )


def downgrade() -> None:
    op.drop_table("video_presence")
