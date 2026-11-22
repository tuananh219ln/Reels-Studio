"""A Page's switch to post its Facebook videos to Instagram too, at the same slot.

Revision ID: 0117
Revises: 0116
"""

import sqlalchemy as sa
from alembic import op

revision = "0117"
down_revision = "0116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Off for every Page: the owner turns it on (jobs.queue_instagram_auto_posts).
    op.add_column("fanpages", sa.Column("instagram_auto", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("fanpages", "instagram_auto")
