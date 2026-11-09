"""A video whose affiliate links a member pasted by hand on Facebook ("Đã dán link tay"): the app keeps out of its
posts' comments

Revision ID: 0072
Revises: 0071
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("manual_comment", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("videos", "manual_comment")
