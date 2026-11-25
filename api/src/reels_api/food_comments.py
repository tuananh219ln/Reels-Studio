"""One detailed comment per dish under a posted reel, written by the member's own assistant (Claude on the web) from
the video's own script, then written under the post by the comment worker like any "Bình luận thêm".

The app calls no AI here: the assistant reads the scenes (`candidates`), writes a comment for each dish and sends them
back (`save`). They are kept in `videos.extra_comments` (post_comments.py writes them in order, each by place, and edits
one whose text changed), and every live Facebook post of the video is asked to write them.

Comments are worth most while a reel is new, so the window is DAYS (decisions/2026-11-18-comment-pacing.md), and a video
scheduled within AHEAD can have its comments ready before it goes live: "Tự bình luận" writes them all then."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import videos
from .errors import ApiError
from .models import KnowledgeTopic, Publication, Video
from .script_rules import banned_hits
from .sessions import now

DAYS = 3
AHEAD = timedelta(hours=48)
MAX_COMMENTS = 12
MIN_LENGTH = 80
MAX_LENGTH = 1500
# Promises a health page may not make (docs/content.md); a comment with one is refused, not just warned about.
CURE_PROMISES = ("chữa khỏi", "khỏi hẳn", "khỏi bệnh", "trị dứt điểm", "điều trị bệnh", "thay thế thuốc", "thay thuốc")


def _facebook_posts(db: DbSession, video_id: int) -> list[Publication]:
    return list(
        db.scalars(select(Publication).where(Publication.video_id == video_id, Publication.platform == "facebook"))
    )


def _live_posts(db: DbSession, video_id: int, since) -> list[Publication]:
    return [
        post
        for post in _facebook_posts(db, video_id)
        if post.remote_id is not None and videos.is_published(post) and videos.live_at(post) >= since
    ]


def _coming_posts(db: DbSession, video_id: int) -> list[Publication]:
    """Posts of the video that will go live within AHEAD: scheduled on Facebook, or still being uploaded."""
    until = now() + AHEAD
    return [
        post
        for post in _facebook_posts(db, video_id)
        if post.status in ("pending", "scheduled")
        and not videos.is_published(post)
        and (post.scheduled_at is None or post.scheduled_at <= until)
    ]


def candidates(db: DbSession, user_id: int, days: int = DAYS) -> list[dict]:
    """The member's videos live on Facebook within `days` (at most DAYS) or going live within AHEAD, newest first, with
    what each dish scene says and how many detailed comments the video already holds, for the assistant to write from."""
    since = now() - timedelta(days=min(days, DAYS))
    found = []
    for video in db.scalars(select(Video).where(Video.created_by_id == user_id).order_by(Video.id.desc())):
        posts = _live_posts(db, video.id, since)
        coming = _coming_posts(db, video.id)
        if not posts and not coming:
            continue
        title, scenes = videos.split_scenes(db, video)
        found.append(
            {
                "video_id": video.id,
                "title": videos.video_name(video, title),
                "topic": video.topic,
                "manual_comment": video.manual_comment,
                "comments_saved": len(video.extra_comments),
                "posts": [{"post_id": post.id, "live_at": videos.live_at(post).isoformat()} for post in posts],
                # Not live yet: the comments saved now go up with the reel.
                "coming": [
                    {"post_id": post.id, "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None}
                    for post in coming
                ],
                "scenes": [
                    {
                        "scene_id": scene.id,
                        "name": videos.scene_name(scene),
                        "text": scene.text,
                        "voice": scene.voice_text,
                    }
                    for scene in scenes
                ],
            }
        )
    return found


def problems(db: DbSession, video: Video, comments: list[str]) -> list[str]:
    topic = db.get(KnowledgeTopic, video.knowledge_topic_id) if video.knowledge_topic_id else None
    found = []
    for place, text in enumerate(comments, start=1):
        if not MIN_LENGTH <= len(text) <= MAX_LENGTH:
            found.append(f"Bình luận {place}: dài {len(text)} ký tự, cần {MIN_LENGTH}–{MAX_LENGTH}")
        hits = [phrase for phrase in CURE_PROMISES if phrase in text.casefold()]
        hits += banned_hits(text, topic.banned_words if topic else [])
        if hits:
            found.append(f"Bình luận {place}: có từ không được dùng ({', '.join(hits)})")
    return found


def save(db: DbSession, user_id: int, video_id: int, comments: list[str]) -> dict:
    """Replace the video's detailed comments (one per dish, in the scenes' order) and ask the worker to write them
    under each of its posts that went live within DAYS; a post going live within AHEAD writes them when it does.
    Commits."""
    video = db.get(Video, video_id, with_for_update=True)
    if video is None or video.created_by_id != user_id:
        raise ApiError(404, "video_not_found", "Không tìm thấy video của bạn")
    comments = [text.strip() for text in comments]
    comments = [text for text in comments if text]
    if not comments or len(comments) > MAX_COMMENTS:
        raise ApiError(422, "invalid_comments", f"Cần từ 1 đến {MAX_COMMENTS} bình luận, mỗi món một bình luận")
    found = problems(db, video, comments)
    if found:
        raise ApiError(422, "invalid_comments", "; ".join(found))
    posts = _live_posts(db, video.id, now() - timedelta(days=DAYS))
    coming = _coming_posts(db, video.id)
    if not posts and not coming:
        raise ApiError(
            409,
            "post_not_live",
            f"Video không có bài Facebook nào lên trong {DAYS} ngày qua hoặc hẹn đăng trong 48 giờ tới",
        )
    video.extra_comments = comments
    asked = 0
    if not video.manual_comment:
        for post in posts:
            post.comment_requested_at = now()
            asked += 1
    db.commit()
    if video.manual_comment:
        note = "Video đã đánh dấu dán link tay nên app không tự đăng; bình luận đã lưu để dán tay"
    elif coming and not posts:
        note = "Bài chưa lên Facebook; bình luận sẽ được đăng khi reel lên nếu bài bật Tự bình luận"
    else:
        note = None
    return {
        "video_id": video.id,
        "saved": len(comments),
        "posts_asked": asked,
        "posts_coming": len(coming),
        "note": note,
    }
