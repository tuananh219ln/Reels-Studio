"""A video's content strategy and its script by beat (docs/decisions/2026-11-26-strategy-beats.md).

Written by Muse through MCP (`set_video_strategy`) and edited on the video page; empty for every video made before.

Revision ID: 0130
Revises: 0129
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0130"
down_revision = "0129"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("strategy", postgresql.JSONB()))
    op.add_column("videos", sa.Column("beats", postgresql.JSONB()))


def downgrade() -> None:
    op.drop_column("videos", "beats")
    op.drop_column("videos", "strategy")
