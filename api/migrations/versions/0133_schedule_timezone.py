"""The time zone posting times are written in (docs/decisions/2026-11-26-schedule-timezone.md).

Every group is Vietnam and every Page uses its group's zone (or Vietnam for its own times), so no posting moment
changes and no `scheduled_at` is touched.

Revision ID: 0133
Revises: 0132
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0133"
down_revision = "0132"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_topics",
        sa.Column("schedule_timezone", sa.String(40), nullable=False, server_default="Asia/Ho_Chi_Minh"),
    )
    op.add_column("fanpages", sa.Column("schedule_timezone", sa.String(40)))
    op.create_check_constraint(
        "ck_knowledge_topics_schedule_timezone",
        "knowledge_topics",
        "schedule_timezone IN ('Asia/Ho_Chi_Minh', 'America/New_York', 'America/Chicago', 'America/Los_Angeles')",
    )
    op.create_check_constraint(
        "ck_fanpages_schedule_timezone",
        "fanpages",
        "schedule_timezone IS NULL OR schedule_timezone IN "
        "('Asia/Ho_Chi_Minh', 'America/New_York', 'America/Chicago', 'America/Los_Angeles')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_fanpages_schedule_timezone", "fanpages")
    op.drop_constraint("ck_knowledge_topics_schedule_timezone", "knowledge_topics")
    op.drop_column("fanpages", "schedule_timezone")
    op.drop_column("knowledge_topics", "schedule_timezone")
