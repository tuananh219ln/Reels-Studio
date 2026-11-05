"""videos.ai_effects: "AI gợi ý hiệu ứng" chosen when the video was made

Revision ID: 0042
Revises: 0041
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("ai_effects", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("videos", "ai_effects")
