"""The AI image provider an image job uses (chosen when it is queued)

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Empty for jobs from before: the team's default provider at the time they run.
    op.add_column("jobs", sa.Column("image_provider", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "image_provider")
