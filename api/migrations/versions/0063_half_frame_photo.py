"""A photo layer's own photo, for "Ảnh chèn nửa khung" (style "half")

Revision ID: 0063
Revises: 0062
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scene_layers", sa.Column("image_key", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("scene_layers", "image_key")
