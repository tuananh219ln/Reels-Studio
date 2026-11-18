"""'Phân tích đối thủ' v2: the channel's avatar, verified badge and own name; a scan may read only the header.

Revision ID: 0101
Revises: 0100
Create Date: 2026-11-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("competitors", sa.Column("avatar_key", sa.Text(), nullable=True))
    op.add_column("competitors", sa.Column("is_verified", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("competitors", sa.Column("custom_name", sa.String(200), nullable=True))
    op.add_column("competitors", sa.Column("meta_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("competitor_scans", sa.Column("meta_only", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("competitor_scans", "meta_only")
    for column in ("meta_updated_at", "custom_name", "is_verified", "avatar_key"):
        op.drop_column("competitors", column)
