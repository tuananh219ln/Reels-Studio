"""publications: a video posted to a platform

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "publications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remote_id", sa.String(length=64), nullable=True),
        sa.Column("remote_mp4_key", sa.String(length=200), nullable=True),
        sa.Column("finish_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_publications_created_by_id_users"),
        sa.ForeignKeyConstraint(
            ["video_id"], ["videos.id"], name="fk_publications_video_id_videos", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_publications"),
        sa.UniqueConstraint("video_id", "platform", name="uq_publications_video_id_platform"),
    )


def downgrade() -> None:
    op.drop_table("publications")
