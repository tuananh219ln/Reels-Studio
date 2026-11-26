"""The review gate: nothing is scheduled or posted until a member approves the video's MP4
(docs/decisions/2026-11-26-review-gate.md).

One service for every channel (the web, Muse through MCP, "Tự duyệt"), so they cannot disagree:
`approve`, `reject`, `restore`, `ensure_approved` (the gate every posting route and the posting jobs call) and
`after_render` (a new MP4 goes back to review and withdraws what was planned for the old one).

`videos.review_status` is only `pending_review` (the start), `approved` or `rejected`; "scheduled" and "published"
are read from the video's posts, never stored twice.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from .errors import ApiError
from .models import Job, PageQueueItem, Publication, User, Video, VideoEvent
from .script_rules import Checks, Issue
from .videos import active_job, render_signature, run_checks, split_scenes, title_of

log = logging.getLogger(__name__)

PENDING, APPROVED, REJECTED = "pending_review", "approved", "rejected"
CHANNELS = ("web", "muse_chat", "auto")
# Posts that exist only here, never reached a platform: withdrawing one is a status change.
UNSENT_STATUSES = ("pending", "scheduled")
NOT_APPROVED = "Cần duyệt video trước khi đăng"


def record(
    db: DbSession,
    video: Video,
    type: str,
    *,
    actor_id: int | None = None,
    channel: str = "system",
    from_status: str | None = None,
    to_status: str | None = None,
    payload: dict | None = None,
) -> None:
    db.add(
        VideoEvent(
            video_id=video.id,
            type=type,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_id,
            channel=channel,
            payload=payload,
        )
    )


def is_fresh(db: DbSession, video: Video) -> bool:
    """The MP4 shows what the script says now."""
    if not video.mp4_key:
        return False
    title, scenes = split_scenes(db, video)
    return video.rendered_signature == render_signature(video, title, scenes)


def qc_report(db: DbSession, video: Video, checks: Checks | None = None) -> dict:
    """`{"passed": bool, "items": [{code, level, message, scene_id?}]}`: the levels of docs/decisions/2026-11-26:
    `blocker` locks approval, `warn` asks for an acknowledgement. Built from the script checks, the MP4's own QC and
    the review rules, so the web, Muse and "Tự duyệt" read one list."""
    items: list[dict] = []

    def add(code: str, level: str, message: str, issue: Issue | None = None) -> None:
        item = {"code": code, "level": level, "message": message}
        if issue is not None and issue.scene_id is not None:
            item["scene_id"] = issue.scene_id
        items.append(item)

    if not video.mp4_key:
        add("RENDER_NOT_DONE", "blocker", "Video chưa có MP4, hãy render trước")
        return {"passed": False, "items": items}
    if video.mode == "upload":
        # A finished MP4 has no script to check: its soft findings and banned words in what a post says warn.
        from .upload_mp4 import warnings as upload_warnings

        if not video.name:
            add("TITLE_EMPTY", "blocker", "Video chưa có tiêu đề")
        for text in upload_warnings(db, video):
            add("MP4_QC", "warn", text)
        return {"passed": not items, "items": items}
    title, scenes = split_scenes(db, video)
    if not title_of(video, title):
        add("TITLE_EMPTY", "blocker", "Video chưa có tiêu đề")
    if video.rendered_signature != render_signature(video, title, scenes):
        add("RENDER_OUTDATED", "blocker", "MP4 chưa cập nhật theo bản sửa, hãy render lại")
    checks = checks or run_checks(db, video, title, scenes)
    for issue in checks.blocking:
        add("SCRIPT_BLOCKING", "blocker", issue.message, issue)
    for issue in checks.warnings:
        add("SCRIPT_WARNING", "warn", issue.message, issue)
    measured = video.qc or {}
    if measured.get("status", "pass") != "pass":
        for check in measured.get("checks", []):
            if check.get("status") != "pass":
                add("MP4_QC", "warn", check.get("detail") or check.get("label") or "Kiểm tra MP4 chưa đạt")
    return {"passed": not items, "items": items}


def payload(db: DbSession, video: Video, checks: Checks | None = None) -> dict:
    """What the video page and Muse read: where the review stands and what stops or warns about approving."""
    approver = db.get(User, video.approved_by_id) if video.approved_by_id else None
    report = qc_report(db, video, checks)
    return {
        "status": video.review_status,
        "approved_at": video.approved_at.isoformat() if video.approved_at else None,
        "approved_via": video.approved_via,
        "approved_by": approver.name if approver else None,
        # An approval holds for the MP4 it was given for; false once a render or a script change has outdated it.
        "can_post": publish_blocker(video) is None,
        "qc": report,
    }


def _transition(db: DbSession, video: Video, to: str, type: str, user_id: int | None, via: str, payload=None) -> None:
    was = video.review_status
    video.review_status = to
    record(db, video, type, actor_id=user_id, channel=via, from_status=was, to_status=to, payload=payload)


def approve(db: DbSession, video: Video, user_id: int, via: str, acknowledge_qc: bool = False) -> None:
    """Callers hold the video lock. Raises `not_pending`, `render_not_done`, `qc_blocker`, `qc_not_acknowledged`."""
    if video.review_status != PENDING:
        raise ApiError(
            409,
            "not_pending",
            "Video đã được duyệt rồi"
            if video.review_status == APPROVED
            else "Video đã bị bỏ, hãy khôi phục trước khi duyệt",
        )
    job = active_job(db, video.id)
    if not video.mp4_key or (job is not None and job.kind == "render"):
        raise ApiError(409, "render_not_done", "Video chưa render xong, hãy đợi bản render rồi duyệt")
    report = qc_report(db, video)
    blockers = [item for item in report["items"] if item["level"] == "blocker"]
    if blockers:
        raise ApiError(409, "qc_blocker", f"Chưa duyệt được: {blockers[0]['message']}")
    if report["items"] and not acknowledge_qc:
        raise ApiError(
            409,
            "qc_not_acknowledged",
            f"Còn {len(report['items'])} mục kiểm tra chưa đạt (ví dụ: {report['items'][0]['message']}), "
            "hãy xem lại rồi duyệt kèm xác nhận",
        )
    _transition(db, video, APPROVED, "approved", user_id, via, {"qc_items": len(report["items"])})
    video.approved_by_id, video.approved_at, video.approved_via = user_id, datetime.now(UTC), via
    video.approved_signature = video.rendered_signature


def reject(db: DbSession, video: Video, user_id: int, via: str, reason: str | None = None) -> None:
    if video.review_status == REJECTED:
        raise ApiError(409, "not_pending", "Video đã bị bỏ rồi")
    if posting_started(db, video):
        raise ApiError(409, "already_posted", "Video đã hẹn giờ hoặc đã đăng, hãy hủy bài trước khi bỏ video")
    _transition(db, video, REJECTED, "rejected", user_id, via, {"reason": reason} if reason else None)
    _clear_approval(video)
    db.execute(delete(PageQueueItem).where(PageQueueItem.video_id == video.id))


def restore(db: DbSession, video: Video, user_id: int, via: str) -> None:
    if video.review_status != REJECTED:
        raise ApiError(409, "not_rejected", "Video chưa bị bỏ")
    _transition(db, video, PENDING, "restored", user_id, via)


def _clear_approval(video: Video) -> None:
    video.approved_by_id = video.approved_at = video.approved_via = video.approved_signature = None


def posting_started(db: DbSession, video: Video) -> bool:
    return (
        db.scalar(
            select(func.count())
            .select_from(Publication)
            .where(
                Publication.video_id == video.id,
                Publication.status.in_(("pending", "scheduled", "private", "published")),
            )
        )
        > 0
    )


def publish_blocker(video: Video) -> str | None:
    """Why this video may not be scheduled or posted now, or None. The approval holds only for the MP4 it was given for."""
    if (
        video.review_status != APPROVED
        or not video.approved_signature
        or video.approved_signature != video.rendered_signature
    ):
        return NOT_APPROVED
    return None


# The jobs that put a video on a platform: each checks the gate again right before it starts (R3), since a
# re-render, a rejection or a withdrawn approval may have come after it was queued.
POSTING_JOBS = ("publish", "tiktok_publish", "ig_publish", "youtube_publish")


def skip_reason(db: DbSession, job: Job) -> str | None:
    """Why a posting job must not run, or None. A skipped job is logged and kept in the video's events."""
    video = db.get(Video, job.video_id)
    reason = publish_blocker(video) if video is not None else None
    if reason is not None:
        log.warning("Job %s (%s) of video %s skipped: %s", job.id, job.kind, job.video_id, reason)
        record(db, video, "publish_skipped", payload={"job_id": job.id, "kind": job.kind})
        db.commit()
    return reason


def ensure_approved(video: Video) -> None:
    """The gate of every route that schedules or posts a video (never the ones that only record a post made by hand)."""
    if (reason := publish_blocker(video)) is not None:
        raise ApiError(409, "not_approved", reason)


def after_render(db: DbSession, video_id: int) -> None:
    """A render ended: the video goes back to review and what was planned for the old MP4 is withdrawn (R2). Never
    raises: a render that worked must not look failed because of this."""
    try:
        _after_render(db, video_id)
        db.commit()
    except Exception:
        db.rollback()
        log.exception("Review reset of video %s failed", video_id)


def _after_render(db: DbSession, video_id: int) -> None:
    db.expire_all()
    video = db.get(Video, video_id)
    if video is None or not video.mp4_key:
        return
    was = video.review_status
    video.review_status = PENDING
    _clear_approval(video)
    withdrawn = 0
    withdrawn += db.execute(delete(PageQueueItem).where(PageQueueItem.video_id == video.id)).rowcount
    uploaded: list[Publication] = []
    for post in db.scalars(
        select(Publication).where(Publication.video_id == video.id, Publication.status.in_(UNSENT_STATUSES))
    ):
        if post.platform == "facebook" and post.remote_id is not None:
            uploaded.append(post)  # on Facebook already (scheduled there): taken down by the worker, below
            continue
        post.status, post.closed_at = "cancelled", datetime.now(UTC)
        withdrawn += 1
    if uploaded and active_job(db, video.id) is None:
        post = uploaded[0]
        db.add(
            Job(
                video_id=video.id,
                kind="unpublish",
                status="queued",
                created_by_id=post.created_by_id,
                publication_id=post.id,
            )
        )
        withdrawn += 1
    record(
        db,
        video,
        "review_requested",
        from_status=was,
        to_status=PENDING,
        payload={"withdrawn": withdrawn} if withdrawn else None,
    )


def pending_count(db: DbSession) -> int:
    """Videos with an MP4 waiting for a member's decision (the menu's badge)."""
    return db.scalar(
        select(func.count()).select_from(Video).where(Video.review_status == PENDING, Video.mp4_key.is_not(None))
    )
