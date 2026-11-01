"""Where a scene's text box was dragged to (the box's centre in the 1080×1920 frame)

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: a scene from before keeps its text box where the template puts it.
    op.add_column("scenes", sa.Column("text_x", sa.Integer(), nullable=True))
    op.add_column("scenes", sa.Column("text_y", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("scenes", "text_y")
    op.drop_column("scenes", "text_x")
