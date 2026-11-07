"""How a video is built: "slides" (each scene its own photo or clip, as before) or "single" ("Video xuyên suốt": the
title scene's photo or clip runs under every scene, with photo layers for the dishes)

Revision ID: 0054
Revises: 0053
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("mode", sa.String(length=16), nullable=False, server_default="slides"))


def downgrade() -> None:
    op.drop_column("videos", "mode")
