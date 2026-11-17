"""'Phân tích đối thủ': a member's competitors on Facebook, their scans, the videos each scan saw, sample
comments of the most viewed and the reports their Claude saved.

Revision ID: 0097
Revises: 0096
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("competitor_scanner_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "competitors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fb_url", sa.Text(), nullable=False),
        sa.Column("fb_id", sa.String(40), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("followers", sa.BigInteger(), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_id", "fb_url", name="uq_competitors_owner_url"),
        sa.CheckConstraint("kind IN ('page', 'profile')", name="ck_competitors_kind"),
    )
    op.create_index("ix_competitors_owner_id", "competitors", ["owner_id"])
    op.create_table(
        "competitor_scans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("competitor_id", sa.Integer(), sa.ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("scope", JSONB(), nullable=False),
        sa.Column("videos_found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'partial', 'done', 'failed')", name="ck_competitor_scans_status"
        ),
    )
    op.create_index("ix_competitor_scans_competitor_id", "competitor_scans", ["competitor_id"])
    op.create_index("ix_competitor_scans_owner_id", "competitor_scans", ["owner_id"])
    op.create_table(
        "competitor_videos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scan_id", sa.Integer(), sa.ForeignKey("competitor_scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fb_video_id", sa.String(40), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("type", sa.String(8), server_default="reel", nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("views_raw", sa.String(60), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("audio_name", sa.Text(), nullable=True),
        sa.Column("reactions", sa.BigInteger(), nullable=True),
        sa.Column("comments", sa.BigInteger(), nullable=True),
        sa.Column("shares", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("scan_id", "fb_video_id", name="uq_competitor_videos_scan_video"),
        sa.CheckConstraint("type IN ('reel', 'video')", name="ck_competitor_videos_type"),
    )
    op.create_index("ix_competitor_videos_scan_id", "competitor_videos", ["scan_id"])
    op.create_table(
        "competitor_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("competitor_videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("like_count", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_competitor_comments_video_id", "competitor_comments", ["video_id"])
    op.create_table(
        "competitor_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scan_id", sa.Integer(), sa.ForeignKey("competitor_scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("written_by", sa.String(40), server_default="", nullable=False),
        sa.Column("summary", JSONB(), nullable=False),
        sa.Column("topics", JSONB(), nullable=False),
        sa.Column("pain_points", JSONB(), nullable=False),
        sa.Column("recommendations", JSONB(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
    )
    op.create_index("ix_competitor_reports_scan_id", "competitor_reports", ["scan_id"])


def downgrade() -> None:
    op.drop_table("competitor_reports")
    op.drop_table("competitor_comments")
    op.drop_table("competitor_videos")
    op.drop_table("competitor_scans")
    op.drop_table("competitors")
    op.drop_column("users", "competitor_scanner_at")
