"""The review gate: a video is approved before anything is scheduled or posted
(docs/decisions/2026-11-26-review-gate.md).

Every video starts `pending_review`. A video that already has a post that was not cancelled was scheduled or posted
before the gate existed: it stays approved (`approved_via = 'legacy'`, for the MP4 it has now), so nothing already
planned is held back; every other video waits for a member.

Revision ID: 0129
Revises: 0128
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0129"
down_revision = "0128"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "videos",
        sa.Column("review_status", sa.String(16), server_default="pending_review", nullable=False),
    )
    op.add_column("videos", sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")))
    op.add_column("videos", sa.Column("approved_at", sa.DateTime(timezone=True)))
    op.add_column("videos", sa.Column("approved_via", sa.String(16)))
    op.add_column("videos", sa.Column("approved_signature", sa.String(64)))
    op.create_index("ix_videos_review_status", "videos", ["review_status"])
    op.create_table(
        "video_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(24), nullable=False),
        sa.Column("from_status", sa.String(16)),
        sa.Column("to_status", sa.String(16)),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("channel", sa.String(16), server_default="web", nullable=False),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_video_events_video_id", "video_events", ["video_id"])
    op.execute(
        """
        UPDATE videos SET review_status = 'approved', approved_via = 'legacy', approved_at = now(),
            approved_signature = rendered_signature
        WHERE mp4_key IS NOT NULL AND EXISTS (
            SELECT 1 FROM publications p WHERE p.video_id = videos.id AND p.status <> 'cancelled'
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_video_events_video_id", table_name="video_events")
    op.drop_table("video_events")
    op.drop_index("ix_videos_review_status", table_name="videos")
    for column in ("approved_signature", "approved_via", "approved_at", "approved_by_id", "review_status"):
        op.drop_column("videos", column)
