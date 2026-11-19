"""A topic group's "Cảnh kết Theo dõi & Chia sẻ" (outro.py): its new videos end on the shared follow-and-share scene
instead of a closing call to action of their script. Every group starts off.

Revision ID: 0115
Revises: 0114
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0115"
down_revision = "0114"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_topics", sa.Column("outro_cta", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("knowledge_topics", "outro_cta")
