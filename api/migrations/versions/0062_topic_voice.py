"""A topic group's own narration voice, which its new videos start with

Revision ID: 0062
Revises: 0061
Create Date: 2026-11-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_topics", sa.Column("voice_id", sa.String(length=200), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("knowledge_topics", "voice_id")
