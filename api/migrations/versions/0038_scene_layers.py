"""scene_layers: text and sticker layers over a scene for their own seconds (the studio)

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scene_layers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("sticker", sa.String(24), nullable=False, server_default=""),
        sa.Column("start", sa.Float(), nullable=False, server_default="0"),
        sa.Column("seconds", sa.Float(), nullable=False, server_default="2"),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("size", sa.String(8), nullable=False, server_default="medium"),
        sa.Column("style", sa.String(16), nullable=False, server_default="outline"),
        sa.Column("animation", sa.String(16), nullable=False, server_default="fade"),
    )
    op.create_index("ix_scene_layers_scene_id", "scene_layers", ["scene_id"])


def downgrade() -> None:
    op.drop_index("ix_scene_layers_scene_id", table_name="scene_layers")
    op.drop_table("scene_layers")
