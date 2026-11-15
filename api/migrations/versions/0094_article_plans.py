"""A Page's 30-day plan of article scripts (decisions 2026-11-15, "article plan").

- `article_plans`: one per Page: day 1, posts per day and their times, and what "Tạo bằng AI" writes from (topic
  groups, the mix of kinds, the voice).
- `article_plan_slots`: one script on a day and slot, or in the plan's Backlog (both null); the article made from it.

Revision ID: 0094
Revises: 0093
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "article_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "fanpage_id",
            sa.Integer(),
            sa.ForeignKey("fanpages.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("per_day", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("post_times", JSONB(), nullable=False, server_default=sa.text('\'["07:00", "11:30", "20:00"]\'')),
        sa.Column("topic_group_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("kind_mix", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("tone", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("per_day BETWEEN 1 AND 10", name=op.f("ck_article_plans_per_day")),
    )
    op.create_table(
        "article_plan_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id", sa.Integer(), sa.ForeignKey("article_plans.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column("day", sa.Integer(), nullable=True),
        sa.Column("slot", sa.Integer(), nullable=True),
        sa.Column("hook", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("cta", sa.Text(), nullable=False, server_default=""),
        sa.Column("hashtags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("image_brief", sa.Text(), nullable=False, server_default=""),
        sa.Column("image_urls", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("kind", sa.String(32), nullable=True),
        sa.Column(
            "knowledge_topic_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_topics.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("keywords", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source", sa.String(8), nullable=False, server_default="manual"),
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, unique=True
        ),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("(day IS NULL) = (slot IS NULL)", name=op.f("ck_article_plan_slots_day_and_slot")),
        sa.CheckConstraint("day IS NULL OR day BETWEEN 1 AND 30", name=op.f("ck_article_plan_slots_day")),
        sa.CheckConstraint("slot IS NULL OR slot BETWEEN 1 AND 10", name=op.f("ck_article_plan_slots_slot")),
    )
    op.create_index(
        "uq_article_plan_slots_cell",
        "article_plan_slots",
        ["plan_id", "day", "slot"],
        unique=True,
        postgresql_where=sa.text("day IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_article_plan_slots_cell", table_name="article_plan_slots")
    op.drop_table("article_plan_slots")
    op.drop_table("article_plans")
