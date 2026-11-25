"""'Phân tích đối thủ' M5: the posting time a reel's or video's own page showed, as written ("3 ngày", "17 tháng 10").

Revision ID: 0099
Revises: 0098
Create Date: 2026-11-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("competitor_videos", sa.Column("posted_raw", sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column("competitor_videos", "posted_raw")
