"""One row per request the app sends to Gemini or Cloudflare Workers AI, so Cài đặt › Nguồn tư liệu can show how many
it made today (Google has no API for the quota left; Cloudflare's needs an analytics permission).

Revision ID: 0105
Revises: 0104
Create Date: 2026-11-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0105"
down_revision = "0104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_service_calls",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("service", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_service_calls_service_created_at", "ai_service_calls", ["service", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_service_calls_service_created_at", table_name="ai_service_calls")
    op.drop_table("ai_service_calls")
