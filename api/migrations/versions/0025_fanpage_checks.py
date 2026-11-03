"""each Page's token check and its followers by day

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable columns and a new table: the previous api version keeps working during a deploy.
    op.add_column("fanpages", sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("fanpages", sa.Column("check_error", sa.Text(), nullable=True))
    op.add_column("fanpages", sa.Column("check_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("fanpages", sa.Column("followers_count", sa.Integer(), nullable=True))
    op.create_table(
        "fanpage_followers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "fanpage_id",
            sa.Integer(),
            sa.ForeignKey("fanpages.id", ondelete="CASCADE", name="fk_fanpage_followers_fanpage_id_fanpages"),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("followers", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_fanpage_followers"),
    )
    op.create_index("uq_fanpage_followers_fanpage_id_day", "fanpage_followers", ["fanpage_id", "day"], unique=True)


def downgrade() -> None:
    op.drop_table("fanpage_followers")
    op.drop_column("fanpages", "followers_count")
    op.drop_column("fanpages", "check_requested_at")
    op.drop_column("fanpages", "check_error")
    op.drop_column("fanpages", "checked_at")
