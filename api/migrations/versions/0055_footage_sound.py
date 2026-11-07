"""Edit từ footage: a scene's clip may keep its own sound, with the words it says; a sample keeps its timed words

Revision ID: 0055
Revises: 0054
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("video_sound", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("scenes", sa.Column("words", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column(
        "video_references",
        sa.Column(
            "words", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("video_references", "words")
    op.drop_column("scenes", "words")
    op.drop_column("scenes", "video_sound")
