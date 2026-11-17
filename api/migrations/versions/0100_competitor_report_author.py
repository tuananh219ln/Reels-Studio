"""'Phân tích đối thủ' read by the whole team: a saved report keeps the member whose Claude saved it.

Revision ID: 0100
Revises: 0099
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "competitor_reports",
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("competitor_reports", "created_by_id")
