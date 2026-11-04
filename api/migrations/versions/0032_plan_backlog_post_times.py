"""30-day plan: a backlog of ideas without a day, and the posting times of each topic group

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

DEFAULT_POST_TIMES = '\'["07:00", "11:30", "17:00", "20:00", "21:30"]\'::jsonb'


def upgrade() -> None:
    # An idea with no day waits in the group's Backlog.
    op.drop_constraint(op.f("ck_topic_plan_items_day"), "topic_plan_items", type_="check")
    op.alter_column("topic_plan_items", "day", existing_type=sa.Integer(), nullable=True)
    op.create_check_constraint(
        op.f("ck_topic_plan_items_day"), "topic_plan_items", "day IS NULL OR day BETWEEN 1 AND 30"
    )
    # The n-th idea of a day is suggested to go out at the n-th time.
    op.add_column(
        "knowledge_topics",
        sa.Column("plan_post_times", JSONB(), server_default=sa.text(DEFAULT_POST_TIMES), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("knowledge_topics", "plan_post_times")
    op.execute("DELETE FROM topic_plan_items WHERE day IS NULL")
    op.drop_constraint(op.f("ck_topic_plan_items_day"), "topic_plan_items", type_="check")
    op.alter_column("topic_plan_items", "day", existing_type=sa.Integer(), nullable=False)
    op.create_check_constraint(op.f("ck_topic_plan_items_day"), "topic_plan_items", "day BETWEEN 1 AND 30")
