"""scenes.transition and scenes.color: a scene's own transition into it and its colour preset (the studio)

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Null for every scene already there: it takes the video's transition and is shown as shot, as before.
    op.add_column("scenes", sa.Column("transition", sa.String(16), nullable=True))
    op.add_column("scenes", sa.Column("color", sa.String(24), nullable=True))


def downgrade() -> None:
    op.drop_column("scenes", "color")
    op.drop_column("scenes", "transition")
