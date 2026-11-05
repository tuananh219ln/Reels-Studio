"""scene_sounds, scenes.music_level and videos.music_start: the studio's sound (sound effects, a scene's own music
level, where the song starts)

Revision ID: 0039
Revises: 0038
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scene_sounds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sound", sa.String(24), nullable=False),
        sa.Column("start", sa.Float(), nullable=False, server_default="0"),
        sa.Column("volume", sa.String(8), nullable=False, server_default="normal"),
    )
    op.create_index("ix_scene_sounds_scene_id", "scene_sounds", ["scene_id"])
    # Null and 0 for what is already there: the music plays as before.
    op.add_column("scenes", sa.Column("music_level", sa.String(8), nullable=True))
    op.add_column("videos", sa.Column("music_start", sa.Float(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("videos", "music_start")
    op.drop_column("scenes", "music_level")
    op.drop_index("ix_scene_sounds_scene_id", table_name="scene_sounds")
    op.drop_table("scene_sounds")
