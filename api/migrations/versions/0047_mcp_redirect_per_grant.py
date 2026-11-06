"""An MCP grant keeps the callback it goes back to, so Claude Code's loopback port can change per session

Revision ID: 0047
Revises: 0046
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mcp_authorizations", sa.Column("redirect_uri", sa.Text(), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("mcp_authorizations", "redirect_uri")
