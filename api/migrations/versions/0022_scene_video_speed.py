"""a scene's clip speed

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A defaulted column: every scene so far plays at 1×, and the previous api version keeps working during a deploy.
    op.add_column("scenes", sa.Column("video_speed", sa.Float(), server_default="1", nullable=False))


def downgrade() -> None:
    op.drop_column("scenes", "video_speed")
