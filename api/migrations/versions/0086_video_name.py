"""A video's own name in the app's lists ("… (copy)" for "Nhân bản y hệt"), never drawn on the video.

Revision ID: 0086
Revises: 0085
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("name", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "name")
