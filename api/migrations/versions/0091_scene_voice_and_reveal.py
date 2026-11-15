"""For the comment-reading pages (2026-11-15): a scene's own narration voice (null reads with the video's voice, as
every scene did before) and how its card ("Thẻ") shows part by part (`reveal`; null shows it whole).

Revision ID: 0091
Revises: 0090
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("voice_id", sa.String(64), nullable=True))
    op.add_column("scenes", sa.Column("reveal", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("scenes", "reveal")
    op.drop_column("scenes", "voice_id")
