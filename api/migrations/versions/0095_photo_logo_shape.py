"""A brand's logo on an article's photos can be a round or rounded badge with a white ring (default: round with the ring).

Revision ID: 0095
Revises: 0094
Create Date: 2026-11-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("brands", sa.Column("photo_logo_shape", sa.String(8), nullable=False, server_default="circle"))
    op.add_column("brands", sa.Column("photo_logo_border", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column(
        "brands", sa.Column("photo_logo_border_color", sa.String(7), nullable=False, server_default="#FFFFFF")
    )
    op.add_column("brands", sa.Column("photo_logo_shadow", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    for name in ("photo_logo_shadow", "photo_logo_border_color", "photo_logo_border", "photo_logo_shape"):
        op.drop_column("brands", name)
