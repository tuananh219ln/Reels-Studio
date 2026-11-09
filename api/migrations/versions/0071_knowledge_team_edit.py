"""A topic group's "Cho cả đội sửa": off, only the group's maker edits it and its plan (2026-11-09)

Revision ID: 0071
Revises: 0070
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every group, old and new, starts open to the whole team, as editing was before.
    op.add_column("knowledge_topics", sa.Column("team_edit", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("knowledge_topics", "team_edit")
