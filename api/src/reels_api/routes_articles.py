"""Articles ("Bài viết"): photo or text posts written for a Page. The draft (articles.py: caption by hand or by the AI;
its photos, article_images.py, with the Page's logo laid on when posted), its posts (article_posts.py: posting, taking
down, checking, the affiliate comment, the numbers) and "Làm reel từ bài này". A request never calls Facebook: the
worker does."""

import tempfile
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from . import (
    affiliate,
    analytics,
    article_images,
    article_posts,
    articles,
    fanpages,
    image_providers,
    remote_media,
)
from .db import get_db
from .errors import ApiError
from .models import (
    ARTICLE_IMAGE_ASPECTS,
    ARTICLE_KINDS,
    PHOTO_LOGO_POSITIONS,
    AffiliateProduct,
    Article,
    ArticleAffiliateProduct,
    Fanpage,
    KnowledgeTopic,
    MediaItem,
    PageComment,
    Publication,
    Session,
)
from .ownership import ensure_can_take_down, ensure_owner, ensure_page_owner
from .routes_affiliate import _ask_comments
from .routes_videos import (
    FIND_IMAGE_SECONDS,
    MAX_KEYWORD_LENGTH,
    MAX_SCHEDULE_DELAY,
    MIN_SCHEDULE_DELAY,
    NewVideoBody,
    clean_stock_order,
    create_video,
    invalid,
    stock_available,
    stock_client,
    stock_orientation,
    stock_turned_off,
)
from .sessions import current_member, now
from .stock_sites import stock_site
from .storage import DirectoryStorage, get_storage
from .uploads import MAX_IMAGE_BYTES, UploadRejected, image_extension, read_limited

router = APIRouter(prefix="/api/articles")

LIST_LIMIT = 200
OPEN_POSTS = ("pending", "scheduled", "published")


class NewArticleBody(BaseModel):
    knowledge_topic_id: int
    kind: str
    topic: str = ""
    source_comment_id: int | None = None


class ArticlePatchBody(BaseModel):
    image_query: str | None = None
    image_prompt: str | None = None
    image_aspect: str | None = None
    knowledge_topic_id: int | None = None
    kind: str | None = None
    topic: str | None = None
    caption: str | None = None
    hashtags: list[str] | None = None
    pinned_comment: str | None = None
    affiliates: list[str] | None = None  # product ideas, one per line on the page
    source_comment_id: int | None = None
    clear_source_comment: bool = False


class TextCardBody(BaseModel):
    preset: str = articles.DEFAULT_CARD_PRESET


class LinkBody(BaseModel):
    url: str


class PublishBody(BaseModel):
    fanpage_id: int
    scheduled_at: datetime | None = None
    # The member saw the warnings (the caption is on another Page, a reel goes out within two hours) and posts anyway.
    confirm: bool = False


class ProductsBody(BaseModel):
    product_ids: list[int]


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
    job = articles.active_job(db, article.id)
    if job is not None:
        doing = "AI đang viết bài này" if job.kind == "article_caption" else "Bài đang có việc chờ hoặc đang chạy"
        raise ApiError(409, "article_busy", f"{doing}, chờ xong rồi làm tiếp")
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
    return article_posts.payload(db, db.get(Article, article.id))


def _options() -> dict:
    return {
        "kinds": [{"value": value, "label": label} for value, label in articles.KIND_LABELS.items()],
        "card_presets": [
            {"value": value, "label": label, "background": background, "color": colour}
            for value, (label, background, colour) in articles.CARD_PRESETS.items()
        ],
        "max_hashtags": articles.MAX_HASHTAGS,
        "max_products": article_posts.MAX_PRODUCTS,
        "product_line": article_posts.PRODUCT_LINE,
        "min_rated_reach": analytics.MIN_RATED_REACH,
        "share_goal": analytics.SHARE_GOAL,
        "min_samples": analytics.MIN_SAMPLES,
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
    by_page = analytics.article_medians(db)
    rows = [article_posts.payload(db, row, by_page) for row in db.scalars(query)]
    return {"articles": rows, **_options()}


@router.get("/options")
def get_options(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """What the editor offers: kinds, card colours, the rules it shows, and the Pages to post to: the member's own in
    use, as only a Page's owner posts to it."""
    pages = [
        {"id": page.id, "name": page.name, "owner": page.owner.name if page.owner else None, "error": page.check_error}
        for page in fanpages.in_use(db)
        if page.owner_id == me.user_id
    ]
    return {**_options(), "fanpages": pages}


@router.get("/attention")
def attention(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """The menu's badge: the member's articles whose post failed and will not be tried again by itself."""
    failed = article_posts.failed_of(db, me.user_id)
    return {"failed": len(failed), "article_ids": failed}


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
    return article_posts.payload(db, _article(db, article_id))


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
    if body.pinned_comment is not None:
        pinned = _text(body.pinned_comment, articles.MAX_PINNED_LENGTH, "Bình luận ghim")
        if pinned != article.pinned_comment:
            article.pinned_comment = pinned
            # A comment already written under a live post is edited to match.
            _ask_comments(db, article)
    if body.affiliates is not None:
        ideas = [" ".join(idea.split())[:100] for idea in body.affiliates if idea.strip()]
        article.affiliates = list(dict.fromkeys(ideas))[:20]
    if body.image_query is not None:
        article.image_query = _text(body.image_query, articles.MAX_IMAGE_QUERY_LENGTH, "Từ khóa tìm ảnh")
    if body.image_prompt is not None:
        article.image_prompt = _text(body.image_prompt, articles.MAX_IMAGE_PROMPT_LENGTH, "Prompt ảnh AI")
    if body.image_aspect is not None:
        if body.image_aspect not in ARTICLE_IMAGE_ASPECTS:
            raise invalid("Tỉ lệ ảnh không hợp lệ")
        article.image_aspect = body.image_aspect
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
    ensure_owner(article.created_by_id, me.user_id, "bài viết này")
    if any(post.status in OPEN_POSTS for post in article_posts.posts_of(db, article.id)):
        raise ApiError(409, "article_posted", "Bài đang chờ đăng, đã hẹn giờ hoặc đã đăng: gỡ bài trên Facebook trước")
    keys = [image.image_key for image in article_images.images_of(db, article.id)]
    db.delete(article)
    db.commit()
    for key in keys:
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


# --- Photos (article_images.py): the same tools as a scene's photo, up to 10, the Page's logo laid on when posted ---


def _added(
    db: DbSession,
    storage: DirectoryStorage,
    article_id: int,
    data: bytes,
    extension: str,
    source: str,
    source_ref: str | None = None,
    credit: str | None = None,
) -> dict:
    article = _editable(db, article_id)
    article_images.add(db, storage, article, data, extension, source, source_ref, credit)
    return _saved(db, article)


def _extension(data: bytes) -> str:
    try:
        return image_extension(data)
    except UploadRejected as err:
        raise ApiError(415, "invalid_image", str(err)) from None


@router.post("/{article_id}/images")
def upload_image(
    article_id: int,
    file: UploadFile = File(...),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """ "Tải lên" and a pasted picture ("Dán…"): the photo added last."""
    article_images.ensure_room(db, _article(db, article_id).id)
    data = read_limited(file, MAX_IMAGE_BYTES, "Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn")
    return _added(db, storage, article_id, data, _extension(data), "upload")


@router.post("/{article_id}/images/text-card")
def make_text_card(
    article_id: int,
    body: TextCardBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """ "Thẻ chữ": the caption's first line on a plain colour, drawn here."""
    article = _editable(db, article_id)
    article_images.ensure_room(db, article.id)
    try:
        data = articles.text_card(articles.hook_of(article.caption), body.preset)
    except articles.CardError as err:
        raise invalid(str(err)) from None
    return _added(db, storage, article_id, data, "jpg", "text_card")


@router.post("/{article_id}/images/from-url")
def image_from_url(
    article_id: int,
    body: LinkBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """A photo pasted as a link (Google Ảnh, a shop...), downloaded like a scene's; the link is kept so a copyright
    claim can be traced."""
    article_images.ensure_room(db, _editable(db, article_id).id)
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
    payload = _added(db, storage, article_id, data, extension, "link", body.url.strip())
    if site := stock_site(body.url):
        payload["notice"] = (
            f"Ảnh này lấy từ {site}: ảnh xem trước thường có watermark và cần mua bản quyền. "
            "Nếu nhóm chưa mua, hãy đổi ảnh khác."
        )
    return payload


class LibraryBody(BaseModel):
    media_id: int


@router.post("/{article_id}/images/library")
def image_from_library(
    article_id: int,
    body: LibraryBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """ "Chọn từ kho" › Kho tư liệu: a copy of the library's photo, so deleting it there leaves the article's."""
    item = db.get(MediaItem, body.media_id)
    if item is None:
        raise ApiError(404, "media_not_found", "Không tìm thấy tư liệu (có thể đã bị xoá)")
    if item.kind != "photo":
        raise invalid("Bài viết chỉ nhận ảnh, không nhận video")
    if not storage.exists(item.storage_key):
        raise ApiError(404, "media_not_found", "File của tư liệu không còn trên máy chủ")
    data = storage.path(item.storage_key).read_bytes()
    extension = item.storage_key.rsplit(".", 1)[-1]
    return _added(db, storage, article_id, data, extension, "library", item.source_url or None)


@router.get("/{article_id}/stock")
def search_stock(
    article_id: int,
    q: str = "",
    source: str | None = None,
    orientation: str = "all",
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """ "Tìm ảnh" for an article: the scene's stock search (the same sources in the order of the article's group, the
    same keys and switches); the results are shown straight from the source."""
    article = _article(db, article_id)
    group = db.get(KnowledgeTopic, article.knowledge_topic_id) if article.knowledge_topic_id else None
    order = clean_stock_order(group.stock_order if group else None)
    source = source or next((item for item in order if stock_available(item, db)), order[0])
    keyword = " ".join(q.split())
    if not keyword:
        raise invalid("Hãy nhập từ khóa tìm ảnh")
    if len(keyword) > MAX_KEYWORD_LENGTH:
        raise invalid(f"Từ khóa dài quá {MAX_KEYWORD_LENGTH} ký tự")
    if source in stock_turned_off(db):
        raise invalid("Nguồn này đang tắt trong Cài đặt › Nguồn tư liệu")
    client, error_type = stock_client(source, db)
    orientation = stock_orientation(orientation)
    db.rollback()
    try:
        hits = client.search_hits(keyword, time.monotonic() + FIND_IMAGE_SECONDS, orientation)
    except error_type as err:
        raise ApiError(502, "stock_error", f"Không tìm được ảnh: {err.message}") from None
    return {
        "keyword": keyword,
        "source": source,
        "hits": [
            {"url": hit.url, "preview": hit.preview, "credit": hit.credit["line"] if hit.credit else None}
            for hit in hits
        ],
    }


class StockChoiceBody(BaseModel):
    source: str
    keyword: str
    url: str
    orientation: str = "all"


@router.post("/{article_id}/images/stock")
def choose_stock(
    article_id: int,
    body: StockChoiceBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """The chosen stock photo, downloaded from its source; it must be one of that source's results for the keyword,
    as for a scene. Its address and any credit line its licence asks for are kept."""
    article_images.ensure_room(db, _editable(db, article_id).id)
    if body.source in stock_turned_off(db):
        raise invalid("Nguồn này đang tắt trong Cài đặt › Nguồn tư liệu")
    client, error_type = stock_client(body.source, db)
    orientation = stock_orientation(body.orientation)
    db.rollback()
    deadline = time.monotonic() + FIND_IMAGE_SECONDS
    try:
        # The address comes from the browser: only a result the source itself returned may be fetched.
        if body.url not in client.search(" ".join(body.keyword.split()), deadline, orientation):
            raise invalid("Ảnh này không có trong kết quả tìm, hãy tìm lại")
        photo = client.download(body.url, deadline)
    except error_type as err:
        raise ApiError(502, "stock_error", f"Không tìm được ảnh: {err.message}") from None
    if photo is None:
        raise ApiError(422, "unusable_image", "Ảnh này không tải được, hãy chọn ảnh khác")
    credit = photo.credit["line"] if photo.credit else None
    return _added(db, storage, article_id, photo.data, photo.extension, "stock", photo.url, credit)


@router.post("/{article_id}/images/ai")
def generate_image(
    article_id: int, provider: str | None = None, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Tạo ảnh AI": a job that makes one photo in the article's shape from its AI prompt (or, without one, its
    photo search words, then its topic) and adds it last. `provider`: the one picked from the arrow for this press;
    the team's default otherwise."""
    article = _editable(db, article_id)
    article_images.ensure_room(db, article.id)
    if not articles.image_prompt_of(article):
        raise invalid("Nhập prompt ảnh AI, từ khóa tìm ảnh hoặc chủ đề của bài trước khi tạo ảnh AI")
    try:
        chosen = image_providers.choose(db, provider)
    except ValueError:
        raise invalid("Nguồn ảnh AI không hợp lệ") from None
    if not articles.enqueue_image(db, article, me.user_id, chosen):
        raise ApiError(409, "article_busy", "Bài đang có việc chờ hoặc đang chạy")
    return _saved(db, article)


class ImagePatchBody(BaseModel):
    logo_enabled: bool | None = None
    # A position of its own for this photo's logo; null: the Page's.
    logo_position: str | None = None


@router.patch("/{article_id}/images/{image_id}")
def patch_image(
    article_id: int,
    image_id: int,
    body: ImagePatchBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """ "Logo ảnh này": the switch and the photo's own logo position."""
    article = _editable(db, article_id)
    image = article_images.get(db, article.id, image_id)
    if body.logo_enabled is not None:
        image.logo_enabled = body.logo_enabled
    if "logo_position" in body.model_fields_set:
        if body.logo_position is not None and body.logo_position not in PHOTO_LOGO_POSITIONS:
            raise invalid("Vị trí logo không hợp lệ")
        image.logo_position = body.logo_position
    return _saved(db, article)


class OrderBody(BaseModel):
    ids: list[int]


@router.put("/{article_id}/images/order")
def order_images(
    article_id: int, body: OrderBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Kéo để đổi thứ tự": the first photo is the one the feed shows biggest."""
    article = _editable(db, article_id)
    article_images.reorder(db, article.id, body.ids)
    return _saved(db, article)


@router.delete("/{article_id}/images/{image_id}")
def remove_image(
    article_id: int,
    image_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """Without photos the article is a text-only post, which is valid."""
    article = _editable(db, article_id)
    image = article_images.get(db, article.id, image_id)
    key = image.image_key
    db.delete(image)
    db.flush()
    article_images.renumber(db, article.id)
    payload = _saved(db, article)
    storage.delete(key)
    return payload


def _photo_file(storage: DirectoryStorage, key: str) -> FileResponse:
    if not storage.exists(key):
        raise ApiError(404, "file_not_found", "Không tìm thấy file")
    extension = key.rsplit(".", 1)[-1]
    media_type = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(extension, "image/jpeg")
    # The address carries the file's tag, so a browser may keep it for good.
    return FileResponse(
        storage.path(key), media_type=media_type, headers={"Cache-Control": "private, max-age=31536000, immutable"}
    )


@router.get("/{article_id}/image")
def first_image(
    article_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    """The first photo, as the list's thumbnail."""
    images = article_images.images_of(db, _article(db, article_id).id)
    if not images:
        raise ApiError(404, "file_not_found", "Bài chưa có ảnh")
    return _photo_file(storage, images[0].image_key)


@router.get("/{article_id}/images/{image_id}")
def image_file(
    article_id: int,
    image_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    return _photo_file(storage, article_images.get(db, article_id, image_id).image_key)


@router.get("/{article_id}/images/{image_id}/preview")
def image_preview(
    article_id: int,
    image_id: int,
    fanpage_id: int | None = None,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> Response:
    """The photo as it will be posted to `fanpage_id`: with that Page's logo where this photo puts it, drawn by the
    same code as the posted copy, 800 px wide."""
    image = article_images.get(db, article_id, image_id)
    if not storage.exists(image.image_key):
        raise ApiError(404, "file_not_found", "Không tìm thấy file")
    return Response(
        article_images.preview(db, storage, image, fanpage_id),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-cache"},
    )


# --- Posting ---


def _post(db: DbSession, post_id: int) -> tuple[Article, Publication]:
    article_id = db.scalar(select(Publication.article_id).where(Publication.id == post_id))
    if article_id is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    article = _article(db, article_id, lock=True)
    post = db.scalar(select(Publication).where(Publication.id == post_id).execution_options(populate_existing=True))
    return article, post


def _queue(db: DbSession, article: Article, kind: str, me: Session, publication_id: int | None = None) -> None:
    if not article_posts.enqueue(db, article, kind, me.user_id, publication_id=publication_id):
        raise ApiError(409, "article_busy", "Bài đang có việc chờ hoặc đang chạy")


@router.post("/{article_id}/publish")
def publish(
    article_id: int, body: PublishBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Đăng": a publish job for the article's one pending post on the chosen Page, now or at a time. The same caption
    is never posted twice on one Page; on another Page, or close to a reel of the Page, the member is asked first
    (409 `confirm_needed`, then again with `confirm`)."""
    article = _editable(db, article_id)
    blocking = articles.checks(article, [])["blocking"]
    if blocking:
        raise ApiError(409, "article_not_ready", blocking[0]["message"])
    when = body.scheduled_at
    if when is not None:
        if when.tzinfo is None:
            raise invalid("Giờ đăng phải kèm múi giờ")
        if not now() + MIN_SCHEDULE_DELAY <= when <= now() + MAX_SCHEDULE_DELAY:
            raise invalid("Giờ hẹn phải sau ít nhất 15 phút và trong vòng 29 ngày tới")
    fanpage = db.get(Fanpage, body.fanpage_id)
    if fanpage is None or not fanpage.active:
        raise invalid("Hãy chọn một Fanpage đang dùng")
    ensure_page_owner(fanpage, me.user_id)
    same_page, others = article_posts.repeats(db, article, fanpage.id)
    if same_page:
        raise ApiError(409, "already_on_page", "Nội dung này đã đăng hoặc đã hẹn trên Page này, không đăng lại được")
    warnings = []
    if others:
        warnings.append(
            f"Nội dung này đã có trên {', '.join(others)}. Đăng cùng nội dung lên nhiều Page dễ bị Facebook coi là "
            "trùng lặp."
        )
    if article_posts.reels_near(db, fanpage.id, when or now()):
        warnings.append("Page này có reel hẹn giờ trong vòng 2 giờ quanh giờ đăng bài.")
    if warnings and not body.confirm:
        raise ApiError(409, "confirm_needed", " ".join(warnings))
    post = article_posts.pending_post(db, article.id)
    if post is None:
        post = Publication(article_id=article.id, platform="facebook", created_by_id=me.user_id)
        db.add(post)
    elif post.remote_id and post.fanpage_id != fanpage.id:
        raise ApiError(409, "other_fanpage", "Bài đã gửi lên Fanpage khác, hãy đăng lại trên Fanpage đó")
    post.fanpage_id, post.scheduled_at, post.created_by_id = fanpage.id, when, me.user_id
    article_posts.reset_retries(post)
    # The comment is the pinned comment, then the products' links: with neither there is nothing to write.
    post.auto_comment = bool(article.pinned_comment.strip() or article_posts.products_of(db, article.id))
    db.flush()
    _queue(db, article, "publish", me)
    return _saved(db, article)


@router.post("/posts/{post_id}/take-down")
def take_down(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Hủy đăng" and "Gỡ bài". A post Facebook never received ends here; any other goes through the worker, which
    decides whether it ends as cancelled or deleted by whether it really went live."""
    article, post = _post(db, post_id)
    ensure_can_take_down(db, post, me.user_id)
    if post.status not in OPEN_POSTS:
        raise ApiError(409, "post_closed", "Bài này đã hủy hoặc đã gỡ")
    job = articles.active_job(db, article.id)
    if job is not None and job.kind == "publish" and job.status == "queued":
        job.status, job.finished_at = "cancelled", now()
        db.flush()
    elif job is not None:
        raise ApiError(409, "article_busy", "Bài đang có việc chạy, hãy đợi xong rồi hủy hoặc gỡ")
    if post.remote_id is None:
        post.status, post.closed_at, post.closed_by_id = "cancelled", now(), me.user_id
    else:
        _queue(db, article, "unpublish", me, publication_id=post.id)
    return _saved(db, article)


@router.post("/posts/{post_id}/check")
def check_post(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Kiểm tra": read the post on Facebook and record what it says."""
    article, post = _post(db, post_id)
    if post.status not in ("scheduled", "published", "deleted") or post.remote_id is None:
        raise ApiError(409, "post_not_checkable", "Chỉ kiểm tra được bài đã lên Facebook, đã hẹn giờ hoặc đã xóa")
    _queue(db, article, "check", me, publication_id=post.id)
    return _saved(db, article)


@router.post("/posts/{post_id}/comment")
def request_comment(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Bình luận ngay": the worker writes the products' comment, or edits it, in its next round."""
    article, post = _post(db, post_id)
    if post.remote_id is None or not article_posts.is_published(post):
        raise ApiError(409, "post_not_live", "Chỉ bình luận được dưới bài đã lên Facebook")
    post.comment_requested_at = now()
    return _saved(db, article)


@router.post("/posts/{post_id}/metrics")
def refresh_metrics(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Cập nhật số": the worker reads the post's numbers in its next round."""
    article, post = _post(db, post_id)
    if post.remote_id is None or not article_posts.is_published(post):
        raise ApiError(409, "post_not_measurable", "Chỉ cập nhật số được cho bài đã đăng lên Facebook")
    post.metrics_requested_at = now()
    return _saved(db, article)


# --- Products ---


@router.get("/{article_id}/product-choices")
def product_choices(article_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list:
    """The group's approved Shopee products that still meet the rules: what may be attached."""
    article = _article(db, article_id)
    rows = db.scalars(
        select(AffiliateProduct)
        .where(
            AffiliateProduct.knowledge_topic_id == article.knowledge_topic_id,
            AffiliateProduct.status == "approved",
            AffiliateProduct.platform == "shopee",
        )
        .order_by(AffiliateProduct.name)
    )
    return [{"id": row.id, "name": row.name} for row in rows if affiliate.usable(row)]


@router.put("/{article_id}/products")
def set_products(
    article_id: int, body: ProductsBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """At most two approved products, whose links go in the comment under the post, never in the caption. A change
    edits comments already written when a member asks for it ("Cập nhật bình luận")."""
    article = _editable(db, article_id)
    ids = list(dict.fromkeys(body.product_ids))
    if len(ids) > article_posts.MAX_PRODUCTS:
        raise invalid(f"Gắn tối đa {article_posts.MAX_PRODUCTS} sản phẩm")
    for product_id in ids:
        product = db.get(AffiliateProduct, product_id)
        if product is None or not affiliate.usable(product) or product.platform != "shopee":
            raise invalid("Chỉ gắn được sản phẩm Shopee đã duyệt")
    before = {product.id for product in article_posts.products_of(db, article.id)}
    db.execute(ArticleAffiliateProduct.__table__.delete().where(ArticleAffiliateProduct.article_id == article.id))
    for product_id in ids:
        db.add(ArticleAffiliateProduct(article_id=article.id, product_id=product_id))
    db.flush()
    if set(ids) != before:
        _ask_comments(db, article)
    return _saved(db, article)


# --- "Làm reel từ bài này" ---


@router.post("/{article_id}/make-video", status_code=201)
def make_video(article_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """A video draft on the article's topic, through the usual "Tạo video" (its script job writes it)."""
    article = _article(db, article_id)
    topic = article.topic or articles.hook_of(article.caption)
    if not topic:
        raise invalid("Bài chưa có chủ đề để làm reel")
    if article.knowledge_topic_id is None:
        raise invalid("Bài chưa thuộc nhóm chủ đề nào")
    video = create_video(NewVideoBody(topic=topic, knowledge_topic_id=article.knowledge_topic_id), me, db)
    return {"video_id": video["id"]}
