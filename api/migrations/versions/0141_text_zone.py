"""Scenes' own "Trên / Dưới" for PC Shopee's text (docs/decisions/2026-11-27-pc-text-tiers.md).

Adds `scenes.text_zone`, null (the lower zone) for every scene already there.

Revision ID: 0141
Revises: 0140
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0141"
down_revision = "0140"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("text_zone", sa.String(6)))


def downgrade() -> None:
    op.drop_column("scenes", "text_zone")
