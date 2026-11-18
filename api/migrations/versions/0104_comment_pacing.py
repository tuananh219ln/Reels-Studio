"""A Page's comment pacing: the earliest time its next comment may be written and how many went out today.

Revision ID: 0104
Revises: 0102
Create Date: 2026-11-18

Branched from 0102 because 0103 (PR #280) is not on main yet: whichever lands second sets its `down_revision` to the
other, so there is one head.
"""

import sqlalchemy as sa
from alembic import op

revision = "0104"
down_revision = "0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fanpages", sa.Column("comments_next_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("fanpages", sa.Column("comments_day", sa.Date(), nullable=True))
    op.add_column("fanpages", sa.Column("comments_count", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    for column in ("comments_count", "comments_day", "comments_next_at"):
        op.drop_column("fanpages", column)
