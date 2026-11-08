"""The assistant that wrote a video's script through MCP (ChatGPT, Claude, Claude Code, Muse), so the video names it

Revision ID: 0059
Revises: 0058
Create Date: 2026-11-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("assistant_app", sa.String(20), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("videos", "assistant_app")
