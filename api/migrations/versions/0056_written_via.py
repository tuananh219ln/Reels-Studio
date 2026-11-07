"""A video's script written by a member's own Claude through MCP is marked, to tell it from the team's AI service

Revision ID: 0056
Revises: 0055
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("written_via", sa.String(20), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("videos", "written_via")
