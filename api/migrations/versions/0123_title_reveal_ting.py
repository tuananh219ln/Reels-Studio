"""Scene sounds know where they came from: "manual" (a member put it there) or "auto_title_reveal" (the "ting" the
title motion places on each slot as it pops in, `slot_index` the slot's number). Draft videos whose title scene still
has the old default pattern (whoosh + ding + rise) switch to "title_sfx": "reveal_ting"; the api then replaces their
sounds the next time the title is built. Rendered, scheduled and posted videos are left alone.

Revision ID: 0123
Revises: 0122
Create Date: 2026-11-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0123"
down_revision = "0122"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scene_sounds", sa.Column("origin", sa.String(20), nullable=False, server_default="manual"))
    op.add_column("scene_sounds", sa.Column("slot_index", sa.Integer(), nullable=True))
    # A draft (never rendered) title scene with a motion title and the old pattern: whoosh, rise and only dings.
    op.execute(
        """
        UPDATE videos SET options = COALESCE(options, '{}'::jsonb) || '{"title_sfx": "reveal_ting"}'::jsonb
        WHERE mp4_key IS NULL
          AND id IN (
            SELECT s.video_id FROM scenes s
            WHERE s.is_title AND jsonb_exists(s.motion, 'title')
              AND EXISTS (SELECT 1 FROM scene_sounds a WHERE a.scene_id = s.id AND a.sound = 'whoosh')
              AND EXISTS (SELECT 1 FROM scene_sounds b WHERE b.scene_id = s.id AND b.sound = 'rise')
              AND NOT EXISTS (
                SELECT 1 FROM scene_sounds c WHERE c.scene_id = s.id AND c.sound NOT IN ('whoosh', 'ding', 'rise')
              )
          )
        """
    )


def downgrade() -> None:
    op.drop_column("scene_sounds", "slot_index")
    op.drop_column("scene_sounds", "origin")
