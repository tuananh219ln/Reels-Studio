"""'Phân tích đối thủ': a small copy of a video's picture for the videos whose own page was opened.

Revision ID: 0105
Revises: 0104
Create Date: 2026-11-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0105"
down_revision = "0104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("competitor_videos", sa.Column("thumb_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("competitor_videos", "thumb_key")
