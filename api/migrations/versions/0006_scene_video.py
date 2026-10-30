"""scene video clips

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only new nullable or defaulted columns: the previous api version keeps working during a deploy.
    op.add_column("scenes", sa.Column("video_key", sa.String(length=200), nullable=True))
    op.add_column("scenes", sa.Column("video_seconds", sa.Float(), nullable=True))
    op.add_column("scenes", sa.Column("video_start", sa.Float(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("scenes", "video_start")
    op.drop_column("scenes", "video_seconds")
    op.drop_column("scenes", "video_key")
