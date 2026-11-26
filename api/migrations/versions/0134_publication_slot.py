"""The slot a Page's queue gave a post (docs/decisions/2026-11-26-schedule-timezone.md).

Null for every post made before and for posts scheduled by hand; nothing is backfilled.

Revision ID: 0134
Revises: 0133
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0134"
down_revision = "0133"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("publications", sa.Column("slot_local", sa.String(5)))
    op.add_column("publications", sa.Column("slot_timezone", sa.String(40)))


def downgrade() -> None:
    op.drop_column("publications", "slot_timezone")
    op.drop_column("publications", "slot_local")
