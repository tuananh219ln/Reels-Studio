"""A topic group's "Chuyển động & âm thanh" (docs/decisions/2026-11-28-group-video-look.md).

Adds `knowledge_topics.video_look`, null (each maker's own defaults) for every group already there.

Revision ID: 0142
Revises: 0141
Create Date: 2026-11-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0142"
down_revision = "0141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_topics", sa.Column("video_look", postgresql.JSONB(none_as_null=True)))


def downgrade() -> None:
    op.drop_column("knowledge_topics", "video_look")
