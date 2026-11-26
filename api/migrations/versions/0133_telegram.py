"""Private Telegram messages to each member (docs/decisions/2026-11-26-telegram-private.md).

A member links their Telegram chat once (Cài đặt › Thông báo Telegram, the bot's /start link); `telegram_notices`
is the bot's outbox, one row per thing a member is told, its key unique per member so nothing is told twice.

Revision ID: 0133
Revises: 0132
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0133"
down_revision = "0132"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_chat_id", sa.BigInteger(), unique=True))
    op.add_column("users", sa.Column("telegram_username", sa.String(64)))
    op.add_column("users", sa.Column("telegram_linked_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("telegram_link_code_hash", sa.String(64)))
    op.add_column("users", sa.Column("telegram_link_expires_at", sa.DateTime(timezone=True)))
    op.add_column(
        "users",
        sa.Column("telegram_muted", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.create_table(
        "telegram_notices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id", ondelete="SET NULL")),
        sa.Column("link", sa.Text()),
        sa.Column("tries", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "key", name="uq_telegram_notices_user_id_key"),
    )
    op.create_index(
        "ix_telegram_notices_unsent", "telegram_notices", ["id"], postgresql_where=sa.text("sent_at IS NULL")
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_notices_unsent", table_name="telegram_notices")
    op.drop_table("telegram_notices")
    for name in (
        "telegram_muted",
        "telegram_link_expires_at",
        "telegram_link_code_hash",
        "telegram_linked_at",
        "telegram_username",
        "telegram_chat_id",
    ):
        op.drop_column("users", name)
