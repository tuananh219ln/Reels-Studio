"""Brands ("Kênh"): one logo per brand, laid on the MP4 at render, and the Facebook Page, TikTok account and YouTube
channel that belong to it. Each existing Page gets a brand of its own (same name, same owner, no logo yet).

Revision ID: 0082
Revises: 0081
Create Date: 2026-11-13
"""

import re
import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def _slug(name: str) -> str:
    plain = unicodedata.normalize("NFD", name.replace("đ", "d").replace("Đ", "D"))
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:100] or "kenh"


def upgrade() -> None:
    brands = op.create_table(
        "brands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("logo_path", sa.String(255)),
        sa.Column("logo_badge_path", sa.String(255)),
        sa.Column("logo_version", sa.String(16)),
        sa.Column("fanpage_id", sa.Integer(), sa.ForeignKey("fanpages.id", ondelete="SET NULL"), unique=True),
        sa.Column("tiktok_username", sa.String(64)),
        sa.Column("tiktok_account_id", sa.String(64)),
        sa.Column("youtube_channel_id", sa.String(64)),
        sa.Column("youtube_handle", sa.String(64)),
        sa.Column("logo_default_on", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    connection = op.get_bind()
    pages = connection.execute(
        sa.text("SELECT id, name, owner_id, updated_by_id FROM fanpages ORDER BY id")
    ).fetchall()
    taken: set[str] = set()
    for page_id, name, owner_id, updated_by_id in pages:
        owner = owner_id or updated_by_id
        if owner is None:
            continue  # nobody to own the brand; its Page is linked to one by hand later
        label, number = name[:120], 1
        while label in taken or _slug(label) in taken:
            number += 1
            label = f"{name[:110]} ({number})"
        taken |= {label, _slug(label)}
        op.bulk_insert(
            brands,
            [{"name": label, "slug": _slug(label), "fanpage_id": page_id, "owner_id": owner, "logo_default_on": True}],
        )


def downgrade() -> None:
    op.drop_table("brands")
