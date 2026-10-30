"""scene narration (TTS)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only new nullable or defaulted columns: the previous api version keeps working during a deploy.
    op.add_column("videos", sa.Column("voice_enabled", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("scenes", sa.Column("voice_text", sa.Text(), server_default="", nullable=False))
    op.add_column("scenes", sa.Column("voice_key", sa.String(length=200), nullable=True))
    op.add_column("scenes", sa.Column("voice_signature", sa.String(length=64), nullable=True))
    op.add_column("scenes", sa.Column("voice_seconds", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("scenes", "voice_seconds")
    op.drop_column("scenes", "voice_signature")
    op.drop_column("scenes", "voice_key")
    op.drop_column("scenes", "voice_text")
    op.drop_column("videos", "voice_enabled")
