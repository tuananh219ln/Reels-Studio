"""TikTok through its API (issue #46): a member's own TikTok connection, the OAuth states on their way, and how a
TikTok post was sent

Revision ID: 0053
Revises: 0052
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tiktok_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("affiliate_account_id", sa.Integer(), nullable=False),
        sa.Column("open_id", sa.String(length=100), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scopes", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_tiktok_connections_owner_id_users"),
        sa.ForeignKeyConstraint(
            ["affiliate_account_id"],
            ["affiliate_accounts.id"],
            name="fk_tiktok_connections_affiliate_account_id_affiliate_accounts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tiktok_connections"),
        sa.UniqueConstraint("affiliate_account_id", name="uq_tiktok_connections_affiliate_account_id"),
        sa.UniqueConstraint("open_id", name="uq_tiktok_connections_open_id"),
    )
    op.create_index("ix_tiktok_connections_owner_id", "tiktok_connections", ["owner_id"])
    op.create_table(
        "tiktok_oauth_states",
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_tiktok_oauth_states_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("state_hash", name="pk_tiktok_oauth_states"),
    )
    op.create_index("ix_tiktok_oauth_states_expires_at", "tiktok_oauth_states", ["expires_at"])
    op.add_column("publications", sa.Column("publish_mode", sa.String(length=16), nullable=True))
    op.add_column("publications", sa.Column("privacy_level", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("publications", "privacy_level")
    op.drop_column("publications", "publish_mode")
    op.drop_index("ix_tiktok_oauth_states_expires_at", table_name="tiktok_oauth_states")
    op.drop_table("tiktok_oauth_states")
    op.drop_index("ix_tiktok_connections_owner_id", table_name="tiktok_connections")
    op.drop_table("tiktok_connections")
