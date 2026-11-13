"""A Page's TikTok account, picked on /fanpages: its videos' Đăng TikTok card opens with it already chosen.

The column was dropped with semi-auto posting (0079); the choice is per Page, not per run, so it comes back
on its own.

Revision ID: 0081
Revises: 0080
Create Date: 2026-11-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fanpages",
        sa.Column(
            "tiktok_account_id",
            sa.Integer(),
            sa.ForeignKey("affiliate_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("fanpages", "tiktok_account_id")
