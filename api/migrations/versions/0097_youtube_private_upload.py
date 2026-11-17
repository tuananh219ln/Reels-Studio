"""YouTube through its API, private only: a member's own YouTube connection, the OAuth states on their way, a Page's
YouTube channel and an upload's resumable session

Revision ID: 0097
Revises: 0096
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "youtube_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("google_channel_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_youtube_connections_owner_id_users"),
        sa.ForeignKeyConstraint(
            ["channel_id"], ["channels.id"], name="fk_youtube_connections_channel_id_channels", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_youtube_connections"),
        sa.UniqueConstraint("channel_id", name="uq_youtube_connections_channel_id"),
        sa.UniqueConstraint("google_channel_id", name="uq_youtube_connections_google_channel_id"),
    )
    op.create_index("ix_youtube_connections_owner_id", "youtube_connections", ["owner_id"])
    op.create_table(
        "youtube_oauth_states",
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_youtube_oauth_states_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("state_hash", name="pk_youtube_oauth_states"),
    )
    op.create_index("ix_youtube_oauth_states_expires_at", "youtube_oauth_states", ["expires_at"])
    op.add_column("fanpages", sa.Column("youtube_channel_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_fanpages_youtube_channel_id_channels",
        "fanpages",
        "channels",
        ["youtube_channel_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("publications", sa.Column("upload_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("publications", "upload_url")
    op.drop_constraint("fk_fanpages_youtube_channel_id_channels", "fanpages", type_="foreignkey")
    op.drop_column("fanpages", "youtube_channel_id")
    op.drop_index("ix_youtube_oauth_states_expires_at", table_name="youtube_oauth_states")
    op.drop_table("youtube_oauth_states")
    op.drop_index("ix_youtube_connections_owner_id", table_name="youtube_connections")
    op.drop_table("youtube_connections")
