"""An article has 1–10 photos (`article_images`), each with the Page's logo laid on it when posted; a brand gains its
photo-logo settings and a white logo for dark photos (decisions 2026-11-15, "article photos and logo").

- `article_images`: the article's photos in order, each with its source, the logo switch and its own position.
- `articles`: the photo search words ("Từ khóa tìm ảnh"), the AI photo prompt and the photos' shape; the one-photo
  columns (`image_key`, `image_kind`, `image_source`) move into `article_images` and go.
- `brands`: the white logo (`logo_alt_path`), and where, how big, how far in and how opaque the logo sits on a photo,
  and the brightness below which the white logo is used.

Revision ID: 0090
Revises: 0089
Create Date: 2026-11-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None

OLD_KINDS = "('ai', 'link', 'text_card')"


def upgrade() -> None:
    op.create_table(
        "article_images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("image_key", sa.String(200), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("credit", sa.Text(), nullable=True),
        sa.Column("logo_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("logo_position", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_article_images_article", "article_images", ["article_id", "position"])
    # A photo an article already had keeps no logo: it was chosen without one, and may already be posted.
    op.execute(
        "INSERT INTO article_images (article_id, position, image_key, source, source_ref, logo_enabled) "
        "SELECT id, 0, image_key, CASE image_kind WHEN 'link' THEN 'link' WHEN 'ai' THEN 'ai' ELSE 'text_card' END, "
        "image_source, false FROM articles WHERE image_key IS NOT NULL"
    )
    op.drop_constraint(op.f("ck_articles_image_kind"), "articles", type_="check")
    for name in ("image_key", "image_kind", "image_source"):
        op.drop_column("articles", name)
    op.add_column("articles", sa.Column("image_query", sa.Text(), nullable=False, server_default=""))
    op.add_column("articles", sa.Column("image_prompt", sa.Text(), nullable=False, server_default=""))
    op.add_column("articles", sa.Column("image_aspect", sa.String(8), nullable=False, server_default="4:5"))

    op.add_column("brands", sa.Column("logo_alt_path", sa.String(255), nullable=True))
    op.add_column("brands", sa.Column("logo_alt_version", sa.String(16), nullable=True))
    op.add_column(
        "brands", sa.Column("photo_logo_position", sa.String(16), nullable=False, server_default="bottom_right")
    )
    op.add_column("brands", sa.Column("photo_logo_size", sa.Float(), nullable=False, server_default="12"))
    op.add_column("brands", sa.Column("photo_logo_margin", sa.Float(), nullable=False, server_default="3"))
    op.add_column("brands", sa.Column("photo_logo_opacity", sa.Float(), nullable=False, server_default="1"))
    op.add_column("brands", sa.Column("photo_logo_alt_threshold", sa.Float(), nullable=True))


def downgrade() -> None:
    for name in (
        "photo_logo_alt_threshold",
        "photo_logo_opacity",
        "photo_logo_margin",
        "photo_logo_size",
        "photo_logo_position",
        "logo_alt_version",
        "logo_alt_path",
    ):
        op.drop_column("brands", name)
    for name in ("image_aspect", "image_prompt", "image_query"):
        op.drop_column("articles", name)
    op.add_column("articles", sa.Column("image_key", sa.String(200), nullable=True))
    op.add_column("articles", sa.Column("image_kind", sa.String(16), nullable=True))
    op.add_column("articles", sa.Column("image_source", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_articles_image_kind"), "articles", f"image_kind IS NULL OR image_kind IN {OLD_KINDS}"
    )
    # Only the first photo fits the old one-photo article; the others' files stay in storage, unread.
    op.execute(
        "UPDATE articles SET image_key = first.image_key, image_source = first.source_ref, "
        "image_kind = CASE first.source WHEN 'link' THEN 'link' WHEN 'ai' THEN 'ai' "
        "WHEN 'text_card' THEN 'text_card' ELSE 'link' END "
        "FROM (SELECT DISTINCT ON (article_id) article_id, image_key, source, source_ref FROM article_images "
        "ORDER BY article_id, position) AS first WHERE first.article_id = articles.id"
    )
    op.drop_index("ix_article_images_article", table_name="article_images")
    op.drop_table("article_images")
