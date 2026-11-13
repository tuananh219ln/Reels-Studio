"""Articles ("Bài viết"): photo or text posts written for a Page. The draft (articles.py: caption by hand or by the AI,
a text card or a pasted photo), its posts (article_posts.py: posting, taking down, checking, the affiliate comment,
the numbers) and "Làm reel từ bài này". A request never calls Facebook: the worker does."""

import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from . import affiliate, analytics, article_posts, articles, fanpages, remote_media
from .db import get_db
from .errors import ApiError
from .models import (
    ARTICLE_KINDS,
    AffiliateProduct,
    Article,
    ArticleAffiliateProduct,
    Fanpage,
    KnowledgeTopic,
    PageComment,
    Publication,
    Session,
)
from .ownership import ensure_can_take_down, ensure_owner, ensure_page_owner
from .routes_affiliate import _ask_comments
from .routes_videos import MAX_SCHEDULE_DELAY, MIN_SCHEDULE_DELAY, NewVideoBody, create_video, invalid
from .sessions import current_member, now
from .storage import DirectoryStorage, get_storage

router = APIRouter(prefix="/api/articles")

LIST_LIMIT = 200
OPEN_POSTS = ("pending", "scheduled", "published")


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
