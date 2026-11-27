"""Word seconds of a scene's narration (docs/decisions/2026-11-27-cumulative-captions.md).

Adds `scenes.voice_words`, null for every narration already made.

Revision ID: 0140
Revises: 0139
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0140"
down_revision = "0139"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("voice_words", postgresql.JSONB()))


def downgrade() -> None:
    op.drop_column("scenes", "voice_words")
