"""scenes.seconds_auto: a scene's seconds follow its narration once the narration is made

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Scenes made before keep the seconds a member may have set by hand; new scenes start following their narration.
    op.add_column("scenes", sa.Column("seconds_auto", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("scenes", "seconds_auto")
