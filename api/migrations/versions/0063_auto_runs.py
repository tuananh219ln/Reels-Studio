"""Semi-automatic posting: a Page's switch, preparing time and TikTok account, and the day's runs ("lượt chạy")

Revision ID: 0063
Revises: 0062
Create Date: 2026-11-08
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fanpages", sa.Column("auto_prepare", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("fanpages", sa.Column("prepare_time", sa.String(length=5), server_default="08:00", nullable=False))
    op.add_column(
        "fanpages",
        sa.Column(
            "tiktok_account_id",
            sa.Integer(),
            sa.ForeignKey("affiliate_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("fanpages", sa.Column("tiktok_own_version", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table(
        "auto_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fanpage_id", sa.Integer(), sa.ForeignKey("fanpages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "plan_item_id", sa.Integer(), sa.ForeignKey("topic_plan_items.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("idea_topic", sa.Text(), server_default="", nullable=False),
        sa.Column("role", sa.String(length=8), server_default="facebook", nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("auto_runs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=16), server_default="script", nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("photos_queued", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("banned", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("skip_tiktok", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("tiktok_state", sa.String(length=16), nullable=True),
        sa.Column("tiktok_reason", sa.Text(), nullable=True),
        sa.Column("publication_id", sa.Integer(), sa.ForeignKey("publications.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "tiktok_publication_id",
            sa.Integer(),
            sa.ForeignKey("publications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_auto_runs_page_day", "auto_runs", ["fanpage_id", "day"])
    # One run per idea, day and role: a second round of the same day never makes a second video.
    op.create_index(
        "uq_auto_runs_idea",
        "auto_runs",
        ["fanpage_id", "day", "plan_item_id", "role"],
        unique=True,
        postgresql_where=sa.text("plan_item_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("auto_runs")
    op.drop_column("fanpages", "tiktok_own_version")
    op.drop_column("fanpages", "tiktok_account_id")
    op.drop_column("fanpages", "prepare_time")
    op.drop_column("fanpages", "auto_prepare")
