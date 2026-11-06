"""Posting an article ("Bài viết") to a Page: its posts are `publications` rows with `article_id`, worked on by the
same publish, unpublish and check jobs as a video's, and its affiliate comment is written by post_comments.py.

The rules are the reel's (docs/decisions.md): never posted twice (what was sent is stamped before Facebook is asked,
and a retry looks for that post on the Page first), the Page is chosen when posting, affiliate links go only in the
comment. Two of its own: the same caption is never posted twice on one Page, and posting it on a second Page asks
first; a post within two hours of a reel scheduled on the same Page asks first too.
"""

import unicodedata
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from . import affiliate, analytics, articles, facebook, post_comments
from . import hashtags as hashtag_rules
from .models import (
    AffiliateProduct,
    Article,
    Fanpage,
    Job,
    Publication,
)
from .videos import LIVE_POST_STATUSES, OPEN_POST_STATUSES, is_published, live_at

MAX_PRODUCTS = 2
PRODUCT_LINE = "Link sản phẩm mình để ở bình luận ghim."
REEL_GAP = timedelta(hours=2)
STATUS_LABELS = {
    "draft": "Nháp",
    "publishing": "Đang đăng…",
    "pending": "Chờ đăng",
    "failed": "Đăng lỗi",
    "scheduled": "Đã hẹn giờ",
    "published": "Đã đăng",
    "unpublishing": "Đang gỡ…",
}
POST_LABELS = {
    "pending": "Chờ đăng",
    "scheduled": "Đã hẹn giờ",
    "published": "Đã đăng",
    "cancelled": "Đã hủy",
    "deleted": "Đã gỡ",
}


def posts_of(db: DbSession, article_id: int) -> list[Publication]:
    return list(
        db.scalars(
            select(Publication)
            .where(Publication.article_id == article_id, Publication.platform == "facebook")
            .order_by(Publication.id.desc())
            .execution_options(populate_existing=True)
        )
    )


def pending_post(db: DbSession, article_id: int) -> Publication | None:
    """The post the publish job works on; at most one, by the partial unique index."""
    return next((post for post in posts_of(db, article_id) if post.status == "pending"), None)


def products_of(db: DbSession, article_id: int) -> list[AffiliateProduct]:
    return affiliate.article_products(db, article_id)


def post_text(db: DbSession, article: Article) -> str:
    """What is posted: the caption, the line pointing at the comment when products are attached (never a link), and
    the hashtags at the end."""
    caption = article.caption.strip()
    if products_of(db, article.id) and PRODUCT_LINE.rstrip(".").lower() not in caption.lower():
        caption = f"{caption}\n\n{PRODUCT_LINE}"
    return hashtag_rules.post_text(caption, article.hashtags)


# --- Before posting ---


def comparable(text: str) -> str:
    """The caption as compared for repeats: no accents, case, hashtags, product line or extra spaces."""
    text = text.replace(PRODUCT_LINE, " ")
    text = hashtag_rules.TAG.sub(" ", text)
    plain = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    plain = "".join(char for char in plain if unicodedata.category(char) != "Mn")
    return " ".join(plain.lower().split())


def repeats(db: DbSession, article: Article, fanpage_id: int) -> tuple[bool, list[str]]:
    """Whether the caption is already up, or on its way, on this Page, and the other Pages it is on."""
    mine = comparable(article.caption)
    if not mine:
        return False, []
    rows = db.execute(
        select(Publication, Article.caption, Fanpage.name)
        .join(Article, Article.id == Publication.article_id)
        .outerjoin(Fanpage, Fanpage.id == Publication.fanpage_id)
        .where(Publication.platform == "facebook", Publication.status.in_(OPEN_POST_STATUSES))
    ).all()
    same_page, others = False, []
    for post, caption, page_name in rows:
        if post.article_id == article.id and post.status == "pending":
            continue
        if comparable(post.post_text or caption) != mine:
            continue
        if post.fanpage_id == fanpage_id:
            same_page = True
        elif page_name and page_name not in others:
            others.append(page_name)
    return same_page, others


def reels_near(db: DbSession, fanpage_id: int, at: datetime) -> list[Publication]:
    """The reels on this Page going out within two hours of `at`."""
    when = Publication.scheduled_at
    return list(
        db.scalars(
            select(Publication).where(
                Publication.fanpage_id == fanpage_id,
                Publication.video_id.is_not(None),
                Publication.platform == "facebook",
                Publication.status.in_(("pending", "scheduled")),
                when.is_not(None),
                when > at - REEL_GAP,
                when < at + REEL_GAP,
            )
        )
    )


# --- Payload ---


def _last_publish(db: DbSession, article_id: int) -> Job | None:
    return db.scalar(
        select(Job)
        .where(Job.article_id == article_id, Job.kind == "publish", Job.status.in_(("done", "failed")))
        .order_by(Job.id.desc())
        .limit(1)
    )


def status(db: DbSession, article: Article, posts: list[Publication]) -> str:
    job = articles.active_job(db, article.id)
    if job is not None and job.kind == "publish":
        return "publishing"
    if job is not None and job.kind == "unpublish":
        return "unpublishing"
    if any(is_published(post) for post in posts):
        return "published"
    if any(post.status == "scheduled" for post in posts):
        return "scheduled"
    if any(post.status == "pending" for post in posts):
        last = _last_publish(db, article.id)
        return "failed" if last is not None and last.status == "failed" else "pending"
    return "draft"


def numbers_payload(post: Publication, by_page: dict) -> dict:
    """The post's numbers: `latest` and `48h` (null until read), the last error, `pending` while a reading asked for
    has not run, and its 48-hour reach against its Page's median of articles (analytics.of_article_post)."""
    windows = {row.window: row for row in post.metrics}

    def numbers(row) -> dict | None:
        if row is None:
            return None
        return {
            "reach": row.reach,
            "shares": row.shares,
            "comments": row.comments,
            "reactions": row.reactions,
            "measured_at": row.measured_at.isoformat(),
        }

    mark = windows.get("48h")
    asked, tried = post.metrics_requested_at, post.metrics_tried_at
    return {
        "latest": numbers(windows.get("latest")),
        "at_48h": numbers(mark),
        "error": post.metrics_error,
        "pending": asked is not None and (tried is None or tried < asked),
        "analysis": analytics.of_article_post(
            post, mark.reach if mark else None, mark.shares if mark else None, by_page
        ),
    }


def post_payload(db: DbSession, post: Publication, by_page: dict | None = None) -> dict:
    page = db.get(Fanpage, post.fanpage_id) if post.fanpage_id else None
    shown = "published" if is_published(post) else post.status
    return {
        "id": post.id,
        "fanpage_id": post.fanpage_id,
        "fanpage": page.name if page else None,
        "status": shown,
        "status_label": POST_LABELS.get(shown, shown),
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "live_at": live_at(post).isoformat(),
        "url": post_url(post),
        "can_take_down": post.status in OPEN_POST_STATUSES,
        "can_check": post.status in LIVE_POST_STATUSES and post.remote_id is not None,
        "comment": post_comments.payload(post),
        "numbers": numbers_payload(post, analytics.article_medians(db) if by_page is None else by_page),
        "can_measure": post.remote_id is not None and is_published(post),
        "created_by": post.created_by.name,
    }


def post_url(post: Publication) -> str | None:
    return facebook.post_url(post.remote_id) if post.remote_id and post.status in LIVE_POST_STATUSES else None


def payload(db: DbSession, article: Article, by_page: dict | None = None) -> dict:
    """The article as the pages show it: its content (articles.payload), posts, products and posting status."""
    data = articles.payload(db, article)
    posts = posts_of(db, article.id)
    by_page = analytics.article_medians(db) if by_page is None else by_page
    code = status(db, article, posts)
    last = _last_publish(db, article.id)
    products = products_of(db, article.id)
    data.update(
        {
            "status": code,
            "status_label": STATUS_LABELS[code],
            "posts": [post_payload(db, post, by_page) for post in posts],
            "publish_error": last.error if code == "failed" and last is not None else None,
            "products": [
                {"id": product.id, "name": product.name, "usable": affiliate.usable(product)} for product in products
            ],
            "post_text": post_text(db, article),
            "busy": data["busy"] or articles.active_job(db, article.id) is not None,
        }
    )
    return data


def enqueue(
    db: DbSession,
    article: Article,
    kind: str,
    user_id: int,
    publication_id: int | None = None,
    retry_of_id: int | None = None,
) -> bool:
    """A publish, unpublish or check job for the article; False when it already has one queued or running (the
    partial unique index is the guard), after rolling the transaction back."""
    db.add(
        Job(
            article_id=article.id,
            kind=kind,
            status="queued",
            created_by_id=user_id,
            publication_id=publication_id,
            retry_of_id=retry_of_id,
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return False
    return True
