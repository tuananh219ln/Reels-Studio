"""A topic group's "Kiểu video": slides, "Video xuyên suốt" or by turns on the Vietnam calendar day (2026-11-10)

Revision ID: 0073
Revises: 0072
Create Date: 2026-11-10
"""

import sqlalchemy as sa
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every group, old and new, starts on slides, as its videos were made before: none changes until its owner
    # switches it.
    op.add_column("knowledge_topics", sa.Column("video_mode", sa.String(20), nullable=False, server_default="slides"))


def downgrade() -> None:
    op.drop_column("knowledge_topics", "video_mode")
