"""knowledge_topics.photo_hint: what a topic group's photos show, read by the AI when it writes search keywords

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Empty for every group already there: their scripts are written as before until a member fills it in.
    op.add_column("knowledge_topics", sa.Column("photo_hint", sa.Text(), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("knowledge_topics", "photo_hint")
