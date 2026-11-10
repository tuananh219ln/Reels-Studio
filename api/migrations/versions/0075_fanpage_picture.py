"""A Page's profile picture link, read by the token check (2026-11-10)

Revision ID: 0075
Revises: 0074
Create Date: 2026-11-10
"""

import sqlalchemy as sa
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Filled by each Page's next check (every 12 hours, or "Kiểm tra ngay").
    op.add_column("fanpages", sa.Column("picture_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("fanpages", "picture_url")
