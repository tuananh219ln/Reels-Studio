"""Articles ("Bài viết"): photo or text posts written for a Page (articles.py). This first part makes and edits the
draft (caption by hand or by the AI, a text card or a pasted photo); posting comes later."""

import tempfile
import unicodedata
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from . import articles, remote_media
from .db import get_db
from .errors import ApiError
from .models import ARTICLE_KINDS, Article, KnowledgeTopic, PageComment, Session
from .routes_videos import invalid
from .sessions import current_member
from .storage import DirectoryStorage, get_storage

router = APIRouter(prefix="/api/articles")

LIST_LIMIT = 200


class NewArticleBody(BaseModel):
    knowledge_topic_id: int
    kind: str
    topic: str = ""
    source_comment_id: int | None = None


class ArticlePatchBody(BaseModel):
    knowledge_topic_id: int | None = None
    kind: str | None = None
    topic: str | None = None
    caption: str | None = None
    hashtags: list[str] | None = None
    source_comment_id: int | None = None
    clear_source_comment: bool = False


class TextCardBody(BaseModel):
    preset: str = articles.DEFAULT_CARD_PRESET


class LinkBody(BaseModel):
    url: str


def _not_found() -> ApiError:
    return ApiError(404, "article_not_found", "Không tìm thấy bài viết (có thể đã bị xoá)")


def _article(db: DbSession, article_id: int, lock: bool = False) -> Article:
    query = select(Article).where(Article.id == article_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    article = db.scalar(query)
    if article is None:
        raise _not_found()
    return article


def _editable(db: DbSession, article_id: int) -> Article:
    """Locked, and refused while the AI is writing it, so neither overwrites the other."""
    article = _article(db, article_id, lock=True)
    if articles.active_job(db, article.id) is not None:
        raise ApiError(409, "article_busy", "AI đang viết bài này, chờ xong rồi sửa")
    return article


def _kind(kind: str) -> str:
    if kind not in ARTICLE_KINDS:
        raise invalid("Dạng bài không hợp lệ")
    return kind


def _group(db: DbSession, topic_id: int) -> int:
    if db.get(KnowledgeTopic, topic_id) is None:
        raise invalid("Không tìm thấy nhóm chủ đề")
    return topic_id


def _text(raw: str, limit: int, label: str) -> str:
    value = unicodedata.normalize("NFC", raw.replace("\r\n", "\n")).strip()
    if len(value) > limit:
        raise invalid(f"{label} dài quá {limit} ký tự")
    return value


def _comment(db: DbSession, comment_id: int) -> int:
    if db.get(PageComment, comment_id) is None:
        raise invalid("Không tìm thấy bình luận")
    return comment_id


def _saved(db: DbSession, article: Article) -> dict:
    db.commit()
    return articles.payload(db, db.get(Article, article.id))


def _options() -> dict:
    return {
        "kinds": [{"value": value, "label": label} for value, label in articles.KIND_LABELS.items()],
        "card_presets": [
            {"value": value, "label": label, "background": background, "color": colour}
            for value, (label, background, colour) in articles.CARD_PRESETS.items()
        ],
        "disclaimer": articles.DISCLAIMER,
        "max_hashtags": articles.MAX_HASHTAGS,
    }


@router.get("")
def list_articles(
    topic_id: int | None = None,
    kind: str | None = None,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    query = (
        select(Article)
        .options(joinedload(Article.created_by), joinedload(Article.source_comment))
        .order_by(Article.id.desc())
        .limit(LIST_LIMIT)
    )
    if topic_id is not None:
        query = query.where(Article.knowledge_topic_id == topic_id)
    if kind:
        query = query.where(Article.kind == _kind(kind))
    return {"articles": [articles.payload(db, row) for row in db.scalars(query)], **_options()}


@router.get("/options")
def get_options(me: Session = Depends(current_member)) -> dict:
    return _options()


@router.post("", status_code=201)
def create_article(
    body: NewArticleBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    article = Article(
        knowledge_topic_id=_group(db, body.knowledge_topic_id),
        kind=_kind(body.kind),
        topic=_text(body.topic, articles.MAX_TOPIC_LENGTH, "Chủ đề"),
        source_comment_id=_comment(db, body.source_comment_id) if body.source_comment_id is not None else None,
        created_by_id=me.user_id,
    )
    db.add(article)
    db.flush()
    return _saved(db, article)


@router.get("/{article_id}")
def get_article(article_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return articles.payload(db, _article(db, article_id))


@router.patch("/{article_id}")
def patch_article(
    article_id: int, body: ArticlePatchBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    article = _editable(db, article_id)
    if body.knowledge_topic_id is not None:
        article.knowledge_topic_id = _group(db, body.knowledge_topic_id)
    if body.kind is not None:
        article.kind = _kind(body.kind)
    if body.topic is not None:
        article.topic = _text(body.topic, articles.MAX_TOPIC_LENGTH, "Chủ đề")
    if body.caption is not None:
        article.caption = _text(body.caption, articles.MAX_CAPTION_LENGTH, "Caption")
    if body.hashtags is not None:
        if len(body.hashtags) > articles.MAX_HASHTAGS:
            raise invalid(f"Tối đa {articles.MAX_HASHTAGS} hashtag")
        article.hashtags = articles.clean_hashtags(body.hashtags)
    if body.clear_source_comment:
        article.source_comment_id = None
    elif body.source_comment_id is not None:
        article.source_comment_id = _comment(db, body.source_comment_id)
    return _saved(db, article)


@router.delete("/{article_id}")
def delete_article(
    article_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    article = _editable(db, article_id)
    key = article.image_key
    db.delete(article)
    db.commit()
    storage.delete(key)
    return {"ok": True}


@router.post("/{article_id}/caption")
def write_caption(article_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "AI viết": an article_caption job; the worker replaces the caption and hashtags when it is done."""
    article = _editable(db, article_id)
    if not article.topic.strip():
        raise invalid("Nhập chủ đề của bài trước khi nhờ AI viết")
    if not articles.enqueue_caption(db, article, me.user_id):
        raise ApiError(409, "article_busy", "AI đang viết bài này, chờ xong rồi sửa")
    return _saved(db, article)


def _store_image(
    db: DbSession,
    storage: DirectoryStorage,
    article_id: int,
    data: bytes,
    extension: str,
    kind: str,
    source: str | None,
) -> dict:
    article = _editable(db, article_id)
    old = article.image_key
    key = articles.new_key(article.id, "image", extension)
    storage.save_bytes(key, data)
    article.image_key, article.image_kind, article.image_source = key, kind, source
    payload = _saved(db, article)
    storage.delete(old)
    return payload


@router.post("/{article_id}/text-card")
def make_text_card(
    article_id: int,
    body: TextCardBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """ "Thẻ chữ": the caption's first line on a plain colour, drawn here (no stock photo, so nothing unoriginal)."""
    article = _editable(db, article_id)
    try:
        data = articles.text_card(articles.hook_of(article.caption), body.preset)
    except articles.CardError as err:
        raise invalid(str(err)) from None
    return _store_image(db, storage, article_id, data, "jpg", "text_card", None)


@router.post("/{article_id}/image-from-url")
def image_from_url(
    article_id: int,
    body: LinkBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """A photo pasted as a link, downloaded like a scene's; the link is kept so a copyright claim can be traced."""
    _editable(db, article_id)
    # No row lock may be held while the other site answers; the save locks and re-checks.
    db.rollback()
    with tempfile.TemporaryDirectory(prefix="reels_article_") as folder:
        try:
            media = remote_media.download(body.url, Path(folder))
        except remote_media.RemoteMediaError as err:
            raise invalid(str(err)) from None
    if media.photo is None:
        raise invalid("Link này là video: bài viết chỉ nhận ảnh")
    data, extension = media.photo
    return _store_image(db, storage, article_id, data, extension, "link", body.url.strip())


@router.delete("/{article_id}/image")
def remove_image(
    article_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """Back to a text-only post, which is a valid article."""
    article = _editable(db, article_id)
    old = article.image_key
    article.image_key = article.image_kind = article.image_source = None
    payload = _saved(db, article)
    storage.delete(old)
    return payload


@router.get("/{article_id}/image")
def article_image(
    article_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    article = _article(db, article_id)
    if not article.image_key or not storage.exists(article.image_key):
        raise ApiError(404, "file_not_found", "Không tìm thấy file")
    extension = article.image_key.rsplit(".", 1)[-1]
    media_type = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(extension, "image/jpeg")
    return FileResponse(
        storage.path(article.image_key), media_type=media_type, headers={"Cache-Control": "private, max-age=3600"}
    )
