"""A scene's clip may loop ("Lặp clip") instead of holding its last frame when it is shorter than the scene.

Revision ID: 0085
Revises: 0084
Create Date: 2026-11-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("video_loop", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("scenes", "video_loop")
