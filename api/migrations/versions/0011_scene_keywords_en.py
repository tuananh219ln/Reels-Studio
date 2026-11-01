"""English stock-search keywords on scenes

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only new nullable or defaulted columns: the previous api version keeps working during a deploy.
    op.add_column("scenes", sa.Column("keywords_en", postgresql.JSONB(), server_default="[]", nullable=False))


def downgrade() -> None:
    op.drop_column("scenes", "keywords_en")
