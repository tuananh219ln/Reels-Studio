"""Why a Page's check could not read its linked Instagram account, shown on "Quản lý kênh" (it was only logged), and
every Page in use checked again so the account is read the new way (the id first, the username on its own).

Revision ID: 0112
Revises: 0111
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0112"
down_revision = "0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fanpages", sa.Column("instagram_error", sa.Text(), nullable=True))
    op.execute("UPDATE fanpages SET check_requested_at = now() WHERE active")


def downgrade() -> None:
    op.drop_column("fanpages", "instagram_error")
