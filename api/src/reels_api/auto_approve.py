"""Tự duyệt: a member who turned it on has the videos they made approved by the app the moment a render is done,
exactly as their "Duyệt" button would (the video is scheduled at its plan idea's time on their Page), but only when
nothing needs a person's eye: no warning, a clean MP4 check, a time, a Page. Every other video waits for a manual
"Duyệt". What happened is kept in `auto_approvals` for Muse, which tells the member on WhatsApp
(docs/decisions/2026-11-13-auto-approve.md)."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import plans
from .errors import ApiError
from .models import AutoApproval, Fanpage, KnowledgeTopic, Session, TopicPlanItem, User, Video
from .videos import pending_publication, run_checks, split_scenes

log = logging.getLogger(__name__)


def settle(db: DbSession, video_id: int) -> None:
    """Called once a render job is done. Never raises: a render that worked must not look failed because of this."""
    try:
        _settle(db, video_id)
    except Exception:
        db.rollback()
        log.exception("Auto-approve of video %s failed", video_id)


def _settle(db: DbSession, video_id: int) -> None:
    db.expire_all()
    video = db.get(Video, video_id)
    maker = db.get(User, video.created_by_id) if video is not None else None
    if video is None or maker is None or not maker.auto_approve or not video.mp4_key or not maker.is_active:
        return
    if pending_publication(db, video.id) is not None:
        return  # approved already, by hand or by an earlier render
    reason, page, when = _blocker(db, video, maker)
    if reason is None:
        from .routes_videos import PublishBody, publish

        try:
            publish(
                video.id,
                PublishBody(fanpage_id=page.id, scheduled_at=when, auto_comment=True),
                Session(user_id=maker.id),
                db,
            )
        except ApiError as err:
            db.rollback()
            reason = err.message
    if reason is not None:
        _record(db, video, maker, "held", reason, page, None)
    else:
        _record(db, video, maker, "approved", "", page, when)


def _blocker(db: DbSession, video: Video, maker: User):
    """(why it waits, the Page, the time); no reason means it may go."""
    page = _page_of(db, video, maker)
    idea = db.scalar(select(TopicPlanItem).where(TopicPlanItem.video_id == video.id))
    topic = db.get(KnowledgeTopic, idea.knowledge_topic_id) if idea is not None else None
    when = plans.suggested_post_at(topic, idea) if topic is not None else None
    if when is None:
        return "Kế hoạch chưa có giờ đăng dự kiến cho video này, hoặc giờ đó đã qua", page, None
    if page is None:
        return "Chưa có Page của bạn cho nhóm chủ đề của video này", None, when
    title, scenes = split_scenes(db, video)
    warnings = run_checks(db, video, title, scenes).warnings
    if warnings:
        return f"Video còn cảnh báo: {warnings[0].message}", page, when
    if (video.qc or {}).get("status", "pass") != "pass":
        failed = next((c["detail"] for c in (video.qc or {}).get("checks", []) if c.get("status") != "pass"), "")
        return f"Kiểm tra MP4 chưa đạt{': ' + failed if failed else ''}", page, when
    return None, page, when


def _page_of(db: DbSession, video: Video, maker: User) -> Fanpage | None:
    """The maker's own Page of the video's group, else their only Page: the same choice as the "Duyệt" button."""
    own = list(db.scalars(select(Fanpage).where(Fanpage.owner_id == maker.id, Fanpage.active).order_by(Fanpage.id)))
    of_group = [
        page for page in own if video.knowledge_topic_id and page.knowledge_topic_id == video.knowledge_topic_id
    ]
    if of_group:
        return of_group[0]
    return own[0] if len(own) == 1 else None


def _record(db, video, maker, outcome, reason, page, when) -> None:
    db.add(
        AutoApproval(
            video_id=video.id,
            user_id=maker.id,
            outcome=outcome,
            reason=reason,
            fanpage_name=page.name if page is not None else "",
            scheduled_at=when,
        )
    )
    db.commit()


def recent(db: DbSession, user_id: int, after_id: int, limit: int) -> list[dict]:
    """The member's results after `after_id`, oldest first, so Muse keeps the last id and asks for what is new."""
    rows = db.execute(
        select(AutoApproval, Video.topic)
        .join(Video, Video.id == AutoApproval.video_id)
        .where(AutoApproval.user_id == user_id, AutoApproval.id > after_id)
        .order_by(AutoApproval.id)
        .limit(limit)
    )
    return [
        {
            "id": row.id,
            "video_id": row.video_id,
            "topic": topic,
            "outcome": row.outcome,
            "reason": row.reason,
            "fanpage": row.fanpage_name,
            "scheduled_at": row.scheduled_at.isoformat() if row.scheduled_at else None,
            "created_at": row.created_at.isoformat(),
        }
        for row, topic in rows
    ]
