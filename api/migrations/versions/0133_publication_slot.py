"""The slot a Page's queue gave a post (docs/decisions/2026-11-26-schedule-timezone.md).

Null for every post made before and for posts scheduled by hand; nothing is backfilled.

Revision ID: 0133
Revises: 0132
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0133"
down_revision = "0132"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("publications", sa.Column("slot_local", sa.String(5)))
    op.add_column("publications", sa.Column("slot_timezone", sa.String(40)))


def downgrade() -> None:
    op.drop_column("publications", "slot_timezone")
    op.drop_column("publications", "slot_local")
