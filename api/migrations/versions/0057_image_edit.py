""" "Sửa ảnh": a scene keeps the photo it had before its first edit, and an image_edit job keeps what it was asked

Revision ID: 0057
Revises: 0056
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("image_original_key", sa.String(200)))
    op.add_column("scenes", sa.Column("image_marks", postgresql.JSONB()))
    op.add_column("scenes", sa.Column("video_blur", postgresql.JSONB()))
    op.add_column("jobs", sa.Column("edit_boxes", postgresql.JSONB()))
    op.add_column("jobs", sa.Column("edit_prompt", sa.Text()))


def downgrade() -> None:
    op.drop_column("jobs", "edit_prompt")
    op.drop_column("jobs", "edit_boxes")
    op.drop_column("scenes", "video_blur")
    op.drop_column("scenes", "image_marks")
    op.drop_column("scenes", "image_original_key")
