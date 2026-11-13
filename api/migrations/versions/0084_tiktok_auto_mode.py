"""A Page's auto-post mode to TikTok: a draft in the inbox (default) or a public post.

Revision ID: 0084
Revises: 0083
Create Date: 2026-11-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fanpages", sa.Column("tiktok_auto_mode", sa.String(16), nullable=False, server_default="draft"))


def downgrade() -> None:
    op.drop_column("fanpages", "tiktok_auto_mode")
