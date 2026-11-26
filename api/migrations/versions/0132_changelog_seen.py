"""When each member last saw "Có gì mới" (docs/decisions/2026-11-26-whats-new.md).

The time the newest change they were shown was merged; empty until they first close the window.

Revision ID: 0132
Revises: 0131
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0132"
down_revision = "0131"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("changelog_seen_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("users", "changelog_seen_at")
