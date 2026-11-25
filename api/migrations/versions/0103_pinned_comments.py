"""'Bình luận ghim' for the article plan: comments on a script, a table of the ones written under a post, and the job.

Revision ID: 0103
Revises: 0102
Create Date: 2026-11-18
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None

STATUSES = ("pending", "posted", "pinned", "need_manual_pin", "failed", "skipped")


def upgrade() -> None:
    op.add_column(
        "article_plan_slots",
        sa.Column("pinned_comments", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column("article_plan_slots", sa.Column("pin_index", sa.Integer(), server_default="0", nullable=False))
    op.add_column("article_plan_slots", sa.Column("comments_source", sa.String(8), nullable=True))
    op.add_column(
        "article_plan_slots", sa.Column("comments_edited", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.add_column("article_plan_slots", sa.Column("comments_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("article_plans", sa.Column("audience", sa.String(200), server_default="", nullable=False))
    op.add_column(
        "articles", sa.Column("post_comments_enabled", sa.Boolean(), server_default=sa.true(), nullable=False)
    )
    op.add_column(
        "jobs",
        sa.Column(
            "plan_slot_id", sa.Integer(), sa.ForeignKey("article_plan_slots.id", ondelete="CASCADE"), nullable=True
        ),
    )
    op.add_column("jobs", sa.Column("params", JSONB(), nullable=True))
    op.create_index(
        "uq_jobs_active_slot_comments",
        "jobs",
        ["plan_slot_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running') AND kind = 'slot_comments'"),
    )
    op.create_table(
        "post_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("publication_id", sa.Integer(), sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("script_id", sa.Integer(), sa.ForeignKey("article_plan_slots.id", ondelete="SET NULL")),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("type", sa.String(16)),
        sa.Column("is_pinned", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("fb_comment_id", sa.String(100)),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"status IN {STATUSES}", name=op.f("ck_post_comments_status")),
    )
    op.create_index("ix_post_comments_publication", "post_comments", ["publication_id", "order"])
    op.create_index("ix_post_comments_status_due", "post_comments", ["status", "due_at"])


def downgrade() -> None:
    op.drop_table("post_comments")
    op.drop_index("uq_jobs_active_slot_comments", table_name="jobs")
    op.drop_column("jobs", "params")
    op.drop_column("jobs", "plan_slot_id")
    op.drop_column("articles", "post_comments_enabled")
    op.drop_column("article_plans", "audience")
    for column in ("comments_updated_at", "comments_edited", "comments_source", "pin_index", "pinned_comments"):
        op.drop_column("article_plan_slots", column)
