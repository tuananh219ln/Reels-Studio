"""The Instagram account linked to each Facebook Page (docs/specs/instagram-posting/brief.md): read at the Page's
check, it is where "Đăng bài" › Instagram posts with the Page's own token.

Revision ID: 0111
Revises: 0110
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fanpages", sa.Column("instagram_user_id", sa.String(32), nullable=True))
    op.add_column("fanpages", sa.Column("instagram_username", sa.String(100), nullable=True))
    # Read again at the next check, so a Page linked before this change shows its account within minutes.
    op.execute("UPDATE fanpages SET check_requested_at = now() WHERE active")


def downgrade() -> None:
    op.drop_column("fanpages", "instagram_username")
    op.drop_column("fanpages", "instagram_user_id")
