"""Private ChatGPT OAuth clients, authorizations and revocable connections.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_clients",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "mcp_authorizations",
        sa.Column("ticket_hash", sa.String(64), primary_key=True),
        sa.Column("client_id", sa.String(64), sa.ForeignKey("mcp_clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("challenge", sa.String(128), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("scopes", sa.String(100), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.String(64), unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mcp_authorizations_expires_at", "mcp_authorizations", ["expires_at"])
    op.create_table(
        "mcp_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(64), sa.ForeignKey("mcp_clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scopes", sa.String(100), nullable=False),
        sa.Column("resource", sa.Text(), nullable=False),
        sa.Column("access_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("refresh_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mcp_connections_session_id", "mcp_connections", ["session_id"])


def downgrade() -> None:
    op.drop_table("mcp_connections")
    op.drop_table("mcp_authorizations")
    op.drop_table("mcp_clients")
