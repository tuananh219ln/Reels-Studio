"""The one scene an image job makes a photo for (empty: every scene that has none)

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No foreign key: a scene deleted later keeps its job in the job log; the job checks the scene still exists.
    op.add_column("jobs", sa.Column("scene_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "scene_id")
