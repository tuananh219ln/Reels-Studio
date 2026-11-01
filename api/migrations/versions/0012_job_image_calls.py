"""Provider call count for image jobs, counted like jobs.claude_calls

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only new nullable or defaulted columns: the previous api version keeps working during a deploy.
    op.add_column("jobs", sa.Column("image_calls", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("jobs", "image_calls")
