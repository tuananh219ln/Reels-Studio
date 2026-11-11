"""Inset photo height, and its place flush with the frame's edges (2026-11-11)

Revision ID: 0078
Revises: 0077
Create Date: 2026-11-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None

# 38% of the 1920 px frame; half of it is where the centre of a photo flush with the top edge is.
TALL = 730


def upgrade() -> None:
    op.add_column("scene_layers", sa.Column("height", sa.Integer(), nullable=False, server_default="38"))
    # Photos that were half the frame (centre 480 / 960 / 1440) keep their place: the top one flush with the top
    # edge, the bottom one flush with the bottom edge, the middle one in the middle.
    op.execute(f"UPDATE scene_layers SET y = {TALL // 2} WHERE kind = 'photo' AND style = 'half' AND y < 960")
    op.execute(f"UPDATE scene_layers SET y = {1920 - TALL // 2} WHERE kind = 'photo' AND style = 'half' AND y > 960")


def downgrade() -> None:
    op.execute("UPDATE scene_layers SET y = 480 WHERE kind = 'photo' AND style = 'half' AND y < 960")
    op.execute("UPDATE scene_layers SET y = 1440 WHERE kind = 'photo' AND style = 'half' AND y > 960")
    op.drop_column("scene_layers", "height")
