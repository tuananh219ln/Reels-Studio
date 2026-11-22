"""A Page's switch to upload its Facebook videos to its YouTube channel too, at the same slot.

Revision ID: 0118
Revises: 0117
"""

import sqlalchemy as sa
from alembic import op

revision = "0118"
down_revision = "0117"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Off for every Page: the owner turns it on (jobs.queue_youtube_auto_posts).
    op.add_column("fanpages", sa.Column("youtube_auto", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("fanpages", "youtube_auto")
