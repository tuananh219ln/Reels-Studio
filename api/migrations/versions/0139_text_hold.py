"""Scenes' own "Ẩn chữ sau X giây" (docs/decisions/2026-11-27-text-hold.md).

Adds `scenes.text_hold_sec`, null (follow the video's setting) for every scene already there.

Revision ID: 0139
Revises: 0138
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0139"
down_revision = "0138"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("text_hold_sec", sa.Float()))


def downgrade() -> None:
    op.drop_column("scenes", "text_hold_sec")
