"""Whether a scene's photo was picked by the app ("Tự tìm ảnh") and still waits for a member to check it

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("image_auto", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("scenes", "image_auto")
