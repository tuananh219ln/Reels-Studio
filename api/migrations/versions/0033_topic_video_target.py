"""knowledge_topics.video_target: how many videos a topic group's trial counts towards ("Tiến độ verdict")

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_topics", sa.Column("video_target", sa.Integer()))


def downgrade() -> None:
    op.drop_column("knowledge_topics", "video_target")
