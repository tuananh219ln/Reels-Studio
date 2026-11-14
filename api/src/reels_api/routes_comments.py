"""Visitors' comments under the app's reels and articles, read by the worker (comments_inbox.py), listed for an article
that answers one ("Trả lời bình luận"). The "Bình luận" page that answered, hid and set them aside is gone (decisions
2026-11-10)."""

from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from . import articles, comments_inbox, facebook
from .db import get_db
from .models import Article, Fanpage, PageComment, Publication, Session, Video
from .sessions import current_member
from .videos import split_scenes, video_name

router = APIRouter(prefix="/api/comments")

# The newest comments shown; at 1–3 reels a day followed for 14 days this is weeks of comments.
LIST_LIMIT = 300


def _payload(db: DbSession, comment: PageComment, titles: dict[int, str]) -> dict:
    post = comment.publication
    owner = post.video_id or -post.article_id
    if owner not in titles:
        if post.article_id is not None:
            # A comment under an article ("Bài viết"): named by its first line, linked to the article.
            article = db.get(Article, post.article_id)
            titles[owner] = f"Bài viết: {articles.hook_of(article.caption) or article.topic}"
        else:
            video = db.get(Video, post.video_id)
            title, _ = split_scenes(db, video)
            titles[owner] = video_name(video, title)
    return {
        "id": comment.id,
        "state": comments_inbox.state(comment),
        "author": comment.author_name,
        "message": comment.message,
        "created_at": comment.created_at.isoformat(),
        "reply_text": comment.reply_text,
        "error": comment.error,
        "handled_by": comment.handled_by.name if comment.handled_by else None,
        "url": f"https://www.facebook.com/{comment.remote_id}",
        "post": {
            "id": post.id,
            "video_id": post.video_id,
            "article_id": post.article_id,
            "title": titles[owner],
            "fanpage": post.fanpage.name if post.fanpage else None,
            "fanpage_id": post.fanpage_id,
            "reel_url": (facebook.post_url if post.article_id else facebook.reel_url)(post.remote_id)
            if post.remote_id
            else None,
        },
    }


@router.get("")
def list_comments(
    state: Literal["open", "all"] = "open",
    whose: Literal["all", "mine"] = "all",
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """`open`: comments still waiting for an answer, and those whose reply or hide is on its way or failed. `mine`:
    those under a post the member made or on a Page they own."""
    query = (
        select(PageComment)
        .options(
            joinedload(PageComment.publication).joinedload(Publication.fanpage), joinedload(PageComment.handled_by)
        )
        .order_by(PageComment.created_at.desc(), PageComment.id.desc())
        .limit(LIST_LIMIT)
    )
    if whose == "mine":
        mine = (
            select(Publication.id)
            .outerjoin(Fanpage, Fanpage.id == Publication.fanpage_id)
            .where((Publication.created_by_id == me.user_id) | (Fanpage.owner_id == me.user_id))
        )
        query = query.where(PageComment.publication_id.in_(mine))
    if state == "open":
        query = query.where(
            PageComment.hidden.is_(False),
            PageComment.answered.is_(False),
            PageComment.dismissed_at.is_(None) | PageComment.error.is_not(None),
        )
    titles: dict[int, str] = {}
    rows = [_payload(db, comment, titles) for comment in db.scalars(query).unique()]
    errors = [
        {"fanpage": name, "error": error}
        for name, error in db.execute(
            select(Fanpage.name, Publication.comments_error)
            .join(Fanpage, Fanpage.id == Publication.fanpage_id)
            .where(Publication.comments_error.is_not(None))
            .distinct()
        )
    ]
    last = db.scalar(select(Publication.comments_read_at).order_by(Publication.comments_read_at.desc().nulls_last()))
    return {"comments": rows, "read_errors": errors, "read_at": last.isoformat() if last else None}
