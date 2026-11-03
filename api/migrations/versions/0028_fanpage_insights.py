"""each Page's daily numbers from Page Insights

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fanpages", sa.Column("insights_error", sa.Text(), nullable=True))
    op.create_table(
        "fanpage_insights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "fanpage_id",
            sa.Integer(),
            sa.ForeignKey("fanpages.id", ondelete="CASCADE", name="fk_fanpage_insights_fanpage_id_fanpages"),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("reach", sa.Integer(), nullable=True),
        sa.Column("engagements", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_fanpage_insights"),
    )
    op.create_index("uq_fanpage_insights_fanpage_id_day", "fanpage_insights", ["fanpage_id", "day"], unique=True)


def downgrade() -> None:
    op.drop_table("fanpage_insights")
    op.drop_column("fanpages", "insights_error")
