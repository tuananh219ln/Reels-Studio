"""A Page's Instagram numbers for one day, read at each Page check with `instagram_manage_insights`.

Revision ID: 0119
Revises: 0118
"""

import sqlalchemy as sa
from alembic import op

revision = "0119"
down_revision = "0118"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instagram_insights",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fanpage_id", sa.Integer(), sa.ForeignKey("fanpages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("views", sa.Integer()),
        sa.Column("reach", sa.Integer()),
        sa.Column("interactions", sa.Integer()),
        sa.Column("follows", sa.Integer()),
    )
    op.create_index("uq_instagram_insights_fanpage_id_day", "instagram_insights", ["fanpage_id", "day"], unique=True)
    op.add_column("fanpages", sa.Column("instagram_insights_error", sa.Text()))
    op.add_column("fanpages", sa.Column("instagram_followers_count", sa.Integer()))


def downgrade() -> None:
    op.drop_column("fanpages", "instagram_followers_count")
    op.drop_column("fanpages", "instagram_insights_error")
    op.drop_index("uq_instagram_insights_fanpage_id_day", table_name="instagram_insights")
    op.drop_table("instagram_insights")
