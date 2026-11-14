"""A topic group's "Không dùng cảnh có người" (owner, 2026-11-15): its scenes show no faces or bodies, hands at work
are fine. On for "Ăn Lành Sống Khỏe" only, as the owner asked; every other group starts off.

Revision ID: 0090
Revises: 0089
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_topics", sa.Column("no_people", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE knowledge_topics SET no_people = true WHERE name LIKE 'Ăn Lành Sống Khỏe%'")


def downgrade() -> None:
    op.drop_column("knowledge_topics", "no_people")
