"""fanpages: the team's connected Facebook Pages

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fanpages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("page_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=False),
        sa.Column("token_tail", sa.String(length=8), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name="fk_fanpages_updated_by_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_fanpages"),
        sa.UniqueConstraint("page_id", name="uq_fanpages_page_id"),
    )
    op.add_column("publications", sa.Column("fanpage_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_publications_fanpage_id_fanpages", "publications", "fanpages", ["fanpage_id"], ["id"])
    # The token entered on the short-lived /settings page never reached a post; it is pasted again on /fanpages.
    op.execute("DELETE FROM settings WHERE key IN ('facebook_page_id', 'facebook_page_token')")


def downgrade() -> None:
    op.drop_constraint("fk_publications_fanpage_id_fanpages", "publications", type_="foreignkey")
    op.drop_column("publications", "fanpage_id")
    op.drop_table("fanpages")
