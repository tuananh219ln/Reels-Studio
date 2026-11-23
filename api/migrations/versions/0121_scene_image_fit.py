"""A scene's "Khung ảnh" (reels_render.framing): how its photo fills the 9:16 frame. image_fit null is "Tự động"
(by the photo's shape: a photo between 3:4 and about 4:3 is cut square, a wider one keeps its shape, both laid over
a blurred copy of themselves; a taller one fills the frame); "cover", "whole" or "square" force one way.
image_crop_offset slides the square along the photo's longer side, 0 to 1; null is the middle.

Revision ID: 0121
Revises: 0120
Create Date: 2026-11-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0121"
down_revision = "0120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("image_fit", sa.String(8), nullable=True))
    op.add_column("scenes", sa.Column("image_crop_offset", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("scenes", "image_crop_offset")
    op.drop_column("scenes", "image_fit")
