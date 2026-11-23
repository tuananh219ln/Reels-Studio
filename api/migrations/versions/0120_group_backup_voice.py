"""A topic group's backup voice, read instead when its own voice's keys are all wrong or spent.

Revision ID: 0120
Revises: 0119
"""

import sqlalchemy as sa
from alembic import op

revision = "0120"
down_revision = "0119"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_topics", sa.Column("voice_backup_id", sa.String(length=200), nullable=False, server_default="")
    )


def downgrade() -> None:
    op.drop_column("knowledge_topics", "voice_backup_id")
