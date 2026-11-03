"""videos written by hand, without the AI

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("hand_written", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("videos", "hand_written")
