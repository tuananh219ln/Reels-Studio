"""A channel's "Kiểu tiêu đề": the style a new "Tiêu đề động" starts in on the videos of its Page. null leaves it to the
build (the motion title is shown); "classic" keeps the title's own photo or clip shown after the first build, the
member switching to "Động" on the video; "motion" is the same as null, kept so a member can say it on purpose.

Revision ID: 0122
Revises: 0121
Create Date: 2026-11-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0122"
down_revision = "0121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("brands", sa.Column("title_style", sa.String(8), nullable=True))


def downgrade() -> None:
    op.drop_column("brands", "title_style")
