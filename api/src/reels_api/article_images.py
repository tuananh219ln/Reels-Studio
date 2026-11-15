"""An article's photos (`article_images`): 1–10 in order, taken with the same tools as a scene's photo (upload, a
pasted link, "Kho tư liệu", the stock sources, an AI photo) plus the "Thẻ chữ" text card. The Page's logo is laid on
a copy of each when the article is posted (photo_logo.py), so the stored photo stays as chosen.

Decisions 2026-11-15, "article photos and logo", which reverses "an article never takes a stock photo" (2026-11-06).
"""

import secrets
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from . import brands, photo_logo
from .errors import ApiError
from .models import Article, ArticleImage
from .storage import DirectoryStorage

MAX_IMAGES = 10
SOURCE_LABELS = {
    "upload": "Tải lên",
    "link": "Ảnh từ link",
    "stock": "Kho ảnh",
    "library": "Kho tư liệu",
    "ai": "Ảnh AI",
    "text_card": "Thẻ chữ",
}


def images_of(db: DbSession, article_id: int) -> list[ArticleImage]:
    return list(
        db.scalars(
            select(ArticleImage)
            .where(ArticleImage.article_id == article_id)
            .order_by(ArticleImage.position, ArticleImage.id)
        )
    )


def count(db: DbSession, article_id: int) -> int:
    return db.scalar(select(func.count()).where(ArticleImage.article_id == article_id)) or 0


def full() -> ApiError:
    return ApiError(409, "article_images_full", f"Bài đã đủ {MAX_IMAGES} ảnh, hãy bỏ bớt ảnh trước khi thêm")


def ensure_room(db: DbSession, article_id: int) -> None:
    if count(db, article_id) >= MAX_IMAGES:
        raise full()


def new_key(article_id: int, extension: str) -> str:
    return f"articles/{article_id}/photo-{secrets.token_hex(6)}.{extension}"


def add(
    db: DbSession,
    storage: DirectoryStorage,
    article: Article,
    data: bytes,
    extension: str,
    source: str,
    source_ref: str | None = None,
    credit: str | None = None,
) -> ArticleImage:
    """The photo stored and put last, its logo on. The caller holds the article's row lock (so two adds never take
    the same place) and commits; the file is removed again if the row cannot be added."""
    ensure_room(db, article.id)
    key = new_key(article.id, extension)
    storage.save_bytes(key, data)
    last = db.scalar(select(func.max(ArticleImage.position)).where(ArticleImage.article_id == article.id))
    image = ArticleImage(
        article_id=article.id,
        position=0 if last is None else last + 1,
        image_key=key,
        source=source,
        source_ref=source_ref,
        credit=credit,
    )
    db.add(image)
    try:
        db.flush()
    except Exception:
        storage.delete(key)
        raise
    return image


def get(db: DbSession, article_id: int, image_id: int) -> ArticleImage:
    image = db.get(ArticleImage, image_id)
    if image is None or image.article_id != article_id:
        raise ApiError(404, "article_image_not_found", "Không tìm thấy ảnh này của bài (có thể đã bị bỏ)")
    return image


def reorder(db: DbSession, article_id: int, ids: list[int]) -> None:
    """`ids` must name every photo of the article once; they take positions 0, 1, 2... in that order."""
    images = images_of(db, article_id)
    if sorted(ids) != sorted(image.id for image in images):
        raise ApiError(409, "article_images_changed", "Danh sách ảnh đã đổi, tải lại trang rồi kéo lại")
    by_id = {image.id: image for image in images}
    for position, image_id in enumerate(ids):
        by_id[image_id].position = position


def renumber(db: DbSession, article_id: int) -> None:
    for position, image in enumerate(images_of(db, article_id)):
        image.position = position


def version(image: ArticleImage) -> str:
    """The file's tag, so a browser keeps a photo for good and fetches a replaced one."""
    return image.image_key.rsplit("-", 1)[-1].split(".", 1)[0]


def payload(image: ArticleImage) -> dict:
    base = f"/api/articles/{image.article_id}/images/{image.id}"
    return {
        "id": image.id,
        "position": image.position,
        "source": image.source,
        "source_label": SOURCE_LABELS[image.source],
        "source_ref": image.source_ref,
        "credit": image.credit,
        "logo_enabled": image.logo_enabled,
        "logo_position": image.logo_position,
        "url": f"{base}?v={version(image)}",
        "preview_url": f"{base}/preview?v={version(image)}",
    }


def preview(db: DbSession, storage: DirectoryStorage, image: ArticleImage, fanpage_id: int | None) -> bytes:
    """The photo as it will be posted to that Page, PREVIEW_WIDTH wide: with its logo, or without when the Page has
    none or the photo's switch is off."""
    logo = photo_logo.logo_for_photo(brands.page_logo(db, storage, fanpage_id), image)
    return photo_logo.render(storage.path(image.image_key).read_bytes(), logo, photo_logo.PREVIEW_WIDTH)


def posted_files(
    db: DbSession, storage: DirectoryStorage, article: Article, fanpage_id: int, folder: Path
) -> list[Path]:
    """The article's photos as they go to the Page, in order: each with the Page's logo laid on unless its switch is
    off, written into `folder`. Raises FileNotFoundError naming the photo whose file is gone."""
    brand_logo = brands.page_logo(db, storage, fanpage_id)
    files = []
    for index, image in enumerate(images_of(db, article.id), start=1):
        if not storage.exists(image.image_key):
            raise FileNotFoundError(f"Ảnh {index}")
        data = photo_logo.render(
            storage.path(image.image_key).read_bytes(), photo_logo.logo_for_photo(brand_logo, image)
        )
        target = folder / f"photo-{index:02d}.jpg"
        target.write_bytes(data)
        files.append(target)
    return files
