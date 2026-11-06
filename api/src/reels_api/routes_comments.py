""" "Bình luận": visitors' comments under the app's reels, to answer, hide or set aside. Every action only records what a
member asked for; the worker sends it to Facebook (comments_inbox.py)."""

import unicodedata
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from . import articles, comments_inbox, facebook
from .db import get_db
from .errors import ApiError
from .models import Article, Fanpage, PageComment, Publication, Session, Video
from .routes_videos import invalid
from .sessions import current_member, now
from .videos import split_scenes, title_of

router = APIRouter(prefix="/api/comments")

# The newest comments shown; at 1–3 reels a day followed for 14 days this is weeks of comments.
LIST_LIMIT = 300
MAX_REPLY_LENGTH = 2000


class ReplyBody(BaseModel):
    text: str


class DismissBody(BaseModel):
    dismissed: bool


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
            titles[owner] = title_of(video, title) or video.topic
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


def _comment(db: DbSession, comment_id: int) -> PageComment:
    comment = db.get(PageComment, comment_id, with_for_update=True)
    if comment is None:
        raise ApiError(404, "comment_not_found", "Không tìm thấy bình luận")
    return comment


def _one(db: DbSession, comment: PageComment) -> dict:
    db.commit()
    return _payload(db, comment, {})


@router.get("")
def list_comments(
    state: Literal["open", "all"] = "open", me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """`open`: comments still waiting for an answer, and those whose reply or hide is on its way or failed."""
    query = (
        select(PageComment)
        .options(
            joinedload(PageComment.publication).joinedload(Publication.fanpage), joinedload(PageComment.handled_by)
        )
        .order_by(PageComment.created_at.desc(), PageComment.id.desc())
        .limit(LIST_LIMIT)
    )
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


@router.post("/refresh")
def refresh(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Tải bình luận mới": the worker reads every followed reel within seconds."""
    comments_inbox.ask_for_reading(db)
    db.commit()
    return {"ok": True}


@router.post("/freshen")
def freshen(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Opening the page: the worker reads the reels not read lately, within seconds."""
    asked = comments_inbox.ask_if_stale(db)
    db.commit()
    return {"asked": asked}


@router.post("/{comment_id}/reply")
def reply(
    comment_id: int, body: ReplyBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    text = unicodedata.normalize("NFC", body.text.replace("\r\n", "\n")).strip()
    if not text:
        raise invalid("Hãy viết câu trả lời")
    if len(text) > MAX_REPLY_LENGTH:
        raise invalid(f"Câu trả lời dài quá {MAX_REPLY_LENGTH} ký tự")
    comment = _comment(db, comment_id)
    if comment.reply_id is not None:
        raise ApiError(409, "already_replied", "Bình luận này đã được trả lời qua app")
    if comment.hidden:
        raise ApiError(409, "comment_hidden", "Bình luận này đã bị ẩn")
    comment.reply_text, comment.reply_requested_at, comment.error = text, now(), None
    comment.handled_by_id = me.user_id
    return _one(db, comment)


@router.post("/{comment_id}/hide")
def hide(comment_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    comment = _comment(db, comment_id)
    if not comment.hidden:
        comment.hide_requested_at, comment.error, comment.handled_by_id = now(), None, me.user_id
    return _one(db, comment)


@router.post("/{comment_id}/dismiss")
def dismiss(
    comment_id: int, body: DismissBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Bỏ qua": no answer needed (a thank-you, an emoji); "Bỏ qua" again brings it back."""
    comment = _comment(db, comment_id)
    comment.dismissed_at = now() if body.dismissed else None
    comment.handled_by_id = me.user_id if body.dismissed else comment.handled_by_id
    return _one(db, comment)
