"""A video's own settings (voice, transitions, text style, captions) from its "Thiết lập" tab

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: a video from before keeps rendering with the original template (video_options.DEFAULTS).
    op.add_column("videos", sa.Column("options", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "options")
