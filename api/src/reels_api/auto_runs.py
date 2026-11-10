"""Semi-automatic posting ("Bán tự động", brief docs/specs/semi-auto-posting): each day at a Page's preparing time the
worker makes today's ideas of its group's 30-day plan into rendered videos, which wait for the Page's owner to approve
them. Nothing is ever posted before that: approving schedules the Facebook post at the idea's posting time through the
usual `publish` job, and sends the MP4 to the owner's TikTok inbox as a draft.

Like `page_queue` and `metrics`, a round runs between jobs and never calls an outside service itself: it only queues
the jobs a member could have queued (script, photos, render, clone, publish, tiktok_publish) and reads how they went.
A run (`auto_runs`) is one idea of one day on one Page; a day with nothing to make leaves one "skipped" run saying why.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from . import knowledge, page_queue, plans, tiktok_connections
from .analytics import VIETNAM
from .models import (
    AffiliateAccount,
    AutoRun,
    Fanpage,
    Job,
    KnowledgeTopic,
    Publication,
    TopicPlanItem,
    Video,
)
from .sessions import now
from .videos import (
    OPEN_POST_STATUSES,
    _version,
    active_job,
    lock_video,
    pending_publication,
    publications_of,
    run_checks,
    split_scenes,
)

log = logging.getLogger(__name__)

# What "Tạo bản TikTok" asks for by default on the video page (web videos/[id]/page.tsx).
TIKTOK_REQUEST = (
    "Viết lại cho TikTok: mở đầu bằng một câu hỏi khơi bình luận, caption ngắn, ít hashtag, đổi 1–2 cảnh và ảnh "
    "khác bản Facebook"
)
NO_IDEA = "Hôm nay chưa có ý tưởng trong kế hoạch"
WAITING_FOR_MACHINE = "Đang chờ máy render"


@dataclass
class Actor:
    """Who the worker acts for: the Page's owner, as `routes_videos` reads only `user_id` of a session."""

    user_id: int


# --- Preparing ---


def due_pages(db: DbSession, at: datetime) -> list[Fanpage]:
    """Pages switched on whose preparing time has come today and that have no run for today yet."""
    local = at.astimezone(VIETNAM)
    pages = db.scalars(select(Fanpage).where(Fanpage.auto_prepare, Fanpage.active).order_by(Fanpage.id)).all()
    due = []
    for page in pages:
        hour, minute = (int(part) for part in page.prepare_time.split(":"))
        if (local.hour, local.minute) < (hour, minute):
            continue
        if db.scalar(select(AutoRun.id).where(AutoRun.fanpage_id == page.id, AutoRun.day == local.date())) is None:
            due.append(page)
    return due


def _skip(db: DbSession, page: Fanpage, day: date, reason: str) -> None:
    db.add(AutoRun(fanpage_id=page.id, day=day, status="skipped", stage="done", reason=reason))
    log.info("Auto run, Page %s, %s: %s", page.id, day, reason)


def page_problem(db: DbSession, page: Fanpage) -> str | None:
    """Why the Page cannot be prepared today, said to its owner; None when it can."""
    if page.owner_id is None:
        return "Page chưa có chủ sở hữu"
    if page.check_error:
        return f"Token của Page đang lỗi: {page.check_error}"
    topic = db.get(KnowledgeTopic, page.knowledge_topic_id) if page.knowledge_topic_id else None
    if topic is None:
        return "Page chưa chọn nhóm chủ đề"
    if not topic.script_prompt:
        return f"Nhóm chủ đề “{topic.name}” chưa có prompt viết kịch bản"
    return None


def today_ideas(db: DbSession, topic: KnowledgeTopic, day: date) -> list[TopicPlanItem]:
    """The plan's ideas for that date, in their order; none before the plan starts, after it ends or without a start."""
    number = plans.day_of(topic.plan_start_date, day)
    if number is None or not 1 <= number <= plans.PLAN_DAYS:
        return []
    return list(
        db.scalars(
            select(TopicPlanItem)
            .where(TopicPlanItem.knowledge_topic_id == topic.id, TopicPlanItem.day == number)
            .order_by(TopicPlanItem.position, TopicPlanItem.id)
        )
    )


def prepare(db: DbSession, page: Fanpage, day: date) -> int:
    """Today's runs of the Page, one per idea of the day (never more than the plan holds for it); the caller commits.
    Returns how many runs were started."""
    reason = page_problem(db, page)
    if reason is not None:
        _skip(db, page, day, reason)
        return 0
    topic = db.get(KnowledgeTopic, page.knowledge_topic_id)
    ideas = today_ideas(db, topic, day)
    if not ideas:
        _skip(db, page, day, NO_IDEA)
        return 0
    started = 0
    for idea in ideas:
        run = AutoRun(fanpage_id=page.id, day=day, plan_item_id=idea.id, idea_topic=idea.topic, status="preparing")
        video = db.get(Video, idea.video_id) if idea.video_id else None
        if video is not None and _posted(db, video):
            run.status, run.stage, run.video_id = "skipped", "done", video.id
            run.reason = "Video của ý tưởng đã có lượt đăng Facebook (hẹn giờ hoặc đã đăng)"
            db.add(run)
            continue
        if video is None:
            video = _new_video(db, page, topic, idea, day)
            run.job_id = _queued_job(db, video.id)
        run.video_id = video.id
        run.stage = "photos" if video.has_script else "script"
        db.add(run)
        started += 1
    db.flush()
    return started


def _posted(db: DbSession, video: Video) -> bool:
    return any(
        post.platform == "facebook" and post.status in OPEN_POST_STATUSES for post in publications_of(db, video.id)
    )


def _new_video(db: DbSession, page: Fanpage, topic: KnowledgeTopic, idea: TopicPlanItem, day: date) -> Video:
    """The idea's video, made as "Tạo video" makes it, by the Page's owner, its script queued on the team's LLM, in
    its group's "Kiểu video" of the day prepared ("Xen kẽ theo ngày")."""
    # Imported here: the routes load FastAPI's request machinery, which the worker needs only for this.
    from .routes_videos import NewVideoBody, start_video

    body = NewVideoBody(topic=idea.topic, knowledge_topic_id=topic.id, plan_item_id=idea.id)
    return start_video(body, Actor(page.owner_id), db, on=day)


def _queued_job(db: DbSession, video_id: int) -> int | None:
    job = active_job(db, video_id)
    return job.id if job else None


# --- Following the chain ---


def advance(db: DbSession, run: AutoRun) -> None:
    """One step of a preparing run: waits on the video's job, then queues the next one, until it waits for approval
    or fails with why. The caller commits."""
    video = db.get(Video, run.video_id) if run.video_id else None
    if video is None:
        _fail(run, "Video của lượt chạy đã bị xoá")
        return
    job = active_job(db, video.id)
    if job is not None:
        note = WAITING_FOR_MACHINE if job.node_stage is not None else None
        if run.reason != note:
            run.reason = note
        return
    if run.job_id is not None:
        waited = db.get(Job, run.job_id)
        if waited is not None and waited.status == "failed":
            _fail(run, f"{_JOB_NAMES.get(waited.kind, 'Job')} lỗi: {waited.error or 'không rõ lý do'}")
            return
        run.job_id = None
    run.reason = None
    if run.stage == "script":
        if not video.has_script:
            _fail(run, "Video chưa có kịch bản")
            return
        run.stage = "photos"
    if run.stage == "photos":
        title, scenes = split_scenes(db, video)
        missing = any(issue.field == "image" for issue in run_checks(db, video, title, scenes).blocking)
        if missing and not run.photos_queued:
            # "Tự tìm ảnh" ran after the script unless it is switched off; it runs once more for the run either way.
            run.photos_queued = True
            run.job_id = _queue(db, video, "photos", run)
            return
        run.stage = "render"
    if run.stage == "render":
        if page_queue.problem(db, video) is None:
            run.stage = "tiktok" if run.role == "facebook" else "done"
        else:
            title, scenes = split_scenes(db, video)
            blocking = run_checks(db, video, title, scenes).blocking
            if blocking:
                _fail(run, f"Chưa render được: {blocking[0].message}")
                return
            run.job_id = _queue(db, video, "render", run)
            return
    if run.stage == "tiktok":
        page = db.get(Fanpage, run.fanpage_id)
        if page.tiktok_own_version and tiktok_account_problem(db, page) is None:
            child = _tiktok_child(db, run)
            if child is None:
                _start_tiktok_version(db, run, video, page)
                return
            if child.status == "failed":
                _fail(run, f"Bản TikTok riêng lỗi: {child.reason}")
                return
            if child.status != "ready":
                return
        run.stage = "done"
    if run.stage == "done" and run.role == "facebook":
        run.status = "ready"
        run.banned = banned_warnings(db, video)
        log.info("Auto run %s: video %s waits for approval", run.id, video.id)
    elif run.stage == "done":
        run.status = "ready"


_JOB_NAMES = {
    "script": "Viết kịch bản",
    "clone": "Viết bản TikTok",
    "photos": "Tìm ảnh",
    "render": "Render",
    "publish": "Đăng Facebook",
    "tiktok_publish": "Gửi nháp TikTok",
}


def _fail(run: AutoRun, reason: str) -> None:
    run.status, run.reason = "failed", reason
    log.info("Auto run %s failed: %s", run.id, reason)


def _owner(db: DbSession, run: AutoRun) -> int:
    return db.get(Fanpage, run.fanpage_id).owner_id


def _queue(db: DbSession, video: Video, kind: str, run: AutoRun) -> int:
    job = Job(video_id=video.id, kind=kind, status="queued", created_by_id=_owner(db, run))
    db.add(job)
    db.flush()
    return job.id


def banned_warnings(db: DbSession, video: Video) -> list[str]:
    """The banned-word warnings of the video, as the editor shows them: they never block, they are flagged."""
    title, scenes = split_scenes(db, video)
    return [issue.message for issue in run_checks(db, video, title, scenes).warnings if "từ cấm" in issue.message]


def _tiktok_child(db: DbSession, run: AutoRun) -> AutoRun | None:
    return db.scalar(select(AutoRun).where(AutoRun.parent_id == run.id, AutoRun.role == "tiktok"))


def _start_tiktok_version(db: DbSession, run: AutoRun, video: Video, page: Fanpage) -> None:
    """ "Bản TikTok riêng": cloned as "Tạo bản TikTok" does, then prepared like its parent."""
    from .routes_videos import CloneBody, clone_video
    from .storage import get_storage

    group = knowledge.topic_of(db, video)
    if group is None or not group.clone_prompt:
        _fail(run, "Nhóm chủ đề chưa có prompt nhân bản để làm bản TikTok riêng")
        return
    payload = clone_video(
        video.id, CloneBody(request=TIKTOK_REQUEST, platform="tiktok"), Actor(page.owner_id), db, get_storage()
    )
    clone = db.get(Video, payload["id"])
    child = AutoRun(
        fanpage_id=run.fanpage_id,
        day=run.day,
        plan_item_id=run.plan_item_id,
        idea_topic=run.idea_topic,
        role="tiktok",
        parent_id=run.id,
        video_id=clone.id,
        status="preparing",
        stage="script",
        job_id=_queued_job(db, clone.id),
    )
    db.add(child)
    db.flush()


def run_round(factory: sessionmaker, at: datetime | None = None) -> None:
    """Called by the worker between jobs. A database hiccup must not stop the worker: the next round tries again."""
    try:
        with factory() as db:
            step(db, at)
    except Exception:
        log.exception("Could not run the semi-automatic posting round")


def step(db: DbSession, at: datetime | None = None) -> None:
    """Starts the Pages that are due, moves every preparing run on, and sends approved runs' TikTok drafts; each Page
    and each run is committed on its own, so one failing never holds the others back."""
    at = at or now()
    for page in due_pages(db, at):
        try:
            prepare(db, page, at.astimezone(VIETNAM).date())
            db.commit()
        except IntegrityError:
            db.rollback()
            log.info("Auto runs of Page %s were started meanwhile", page.id)
    # Children first, so a parent finds its TikTok version's newest state.
    preparing = db.scalars(
        select(AutoRun.id).where(AutoRun.status == "preparing").order_by(AutoRun.parent_id.is_(None), AutoRun.id)
    ).all()
    for run_id in preparing:
        run = db.get(AutoRun, run_id)
        if run.video_id is not None:
            lock_video(db, run.video_id)
        advance(db, run)
        db.commit()
    for run_id in db.scalars(select(AutoRun.id).where(AutoRun.tiktok_state == "waiting")).all():
        send_tiktok(db, db.get(AutoRun, run_id))
        db.commit()


# --- Approving ---


class ApprovalError(Exception):
    """The message is shown to members."""


def tiktok_account_problem(db: DbSession, page: Fanpage) -> str | None:
    """Why TikTok is left out for the Page; None when its owner's chosen account is connected."""
    account = db.get(AffiliateAccount, page.tiktok_account_id) if page.tiktok_account_id else None
    if account is None:
        return "Page chưa chọn tài khoản TikTok"
    if account.owner_id != page.owner_id or account.platform != "tiktok" or not account.active:
        return f"Tài khoản “{account.name}” không còn là tài khoản TikTok đang dùng của chủ Page"
    connection = tiktok_connections.of_account(db, account.id)
    if connection is None:
        return f"Tài khoản “{account.name}” chưa kết nối TikTok"
    if tiktok_connections.needs_reconnect(connection):
        return f"Kết nối TikTok của “{account.name}” đã hết hạn, hãy kết nối lại"
    return None


def post_time(db: DbSession, page: Fanpage, run: AutoRun, at: datetime) -> datetime:
    """The idea's posting time on its day (the Page's own times, else its group's: the n-th idea at the n-th time);
    once that is too close or taken, the Page's next free posting time within 48 hours, as its queue does."""
    times = page_queue.post_times(db, page)
    if not times:
        raise ApprovalError("Page và nhóm chủ đề chưa có giờ đăng")
    idea = db.get(TopicPlanItem, run.plan_item_id) if run.plan_item_id else None
    place = idea.position if idea is not None else 1
    hour, minute = (int(part) for part in times[min(place, len(times)) - 1].split(":"))
    wanted = datetime(run.day.year, run.day.month, run.day.day, hour, minute, tzinfo=VIETNAM)
    earliest = at + page_queue.FILL_LEAD
    start = max(wanted, earliest)
    slots = page_queue.free_slots(db, page, start, max(start, earliest + page_queue.FILL_AHEAD))
    if wanted >= earliest and slots and slots[0] == wanted:
        return wanted
    if not slots:
        raise ApprovalError("Page không còn giờ đăng trống trong 48 giờ tới")
    return slots[0]


def approve(db: DbSession, run: AutoRun, user_id: int, skip_tiktok: bool, at: datetime | None = None) -> None:
    """ "Duyệt": the Facebook post scheduled at the idea's time through the usual `publish` job, with the affiliate
    comment; the TikTok draft follows once that job is done (one job per video at a time). The caller commits."""
    at = at or now()
    page = db.get(Fanpage, run.fanpage_id)
    if page.owner_id != user_id:
        raise ApprovalError("Chỉ chủ Page mới duyệt được video của Page")
    if run.status != "ready":
        raise ApprovalError("Lượt chạy không ở trạng thái chờ duyệt")
    video = lock_video(db, run.video_id)
    reason = page_queue.problem(db, video, page)
    if reason is not None:
        raise ApprovalError(reason)
    if active_job(db, video.id) is not None or pending_publication(db, video.id) is not None:
        raise ApprovalError("Video đang có job chạy, hãy đợi xong rồi duyệt")
    if _posted(db, video):
        raise ApprovalError("Video đã có lượt đăng Facebook")
    slot = post_time(db, page, run, at)
    post = Publication(
        video_id=video.id,
        platform="facebook",
        fanpage_id=page.id,
        scheduled_at=slot,
        created_by_id=user_id,
        auto_comment=True,
    )
    db.add(post)
    db.flush()
    db.add(Job(video_id=video.id, kind="publish", status="queued", created_by_id=user_id))
    run.status, run.publication_id = "approved", post.id
    run.decided_by_id, run.decided_at, run.skip_tiktok = user_id, at, skip_tiktok
    if skip_tiktok:
        run.tiktok_state, run.tiktok_reason = "skipped", "Bỏ qua TikTok khi duyệt"
    elif (problem := tiktok_account_problem(db, page)) is not None:
        run.tiktok_state, run.tiktok_reason = "skipped", problem
    else:
        run.tiktok_state = "waiting"
    db.flush()
    log.info("Auto run %s approved: video %s at %s", run.id, video.id, slot.isoformat())


def reject(db: DbSession, run: AutoRun, user_id: int, at: datetime | None = None) -> None:
    """ "Không duyệt": nothing is posted; the video stays to be fixed by hand."""
    page = db.get(Fanpage, run.fanpage_id)
    if page.owner_id != user_id:
        raise ApprovalError("Chỉ chủ Page mới duyệt được video của Page")
    if run.status != "ready":
        raise ApprovalError("Lượt chạy không ở trạng thái chờ duyệt")
    run.status, run.decided_by_id, run.decided_at = "rejected", user_id, at or now()


def tiktok_video_id(db: DbSession, run: AutoRun) -> int:
    child = _tiktok_child(db, run)
    return child.video_id if child is not None and child.status == "ready" else run.video_id


def send_tiktok(db: DbSession, run: AutoRun) -> None:
    """The approved run's TikTok draft, once the video has no job running (the Facebook post's job goes first)."""
    video_id = tiktok_video_id(db, run)
    video = lock_video(db, video_id)
    if active_job(db, video.id) is not None:
        return
    page = db.get(Fanpage, run.fanpage_id)
    problem = tiktok_account_problem(db, page)
    if problem is not None:
        run.tiktok_state, run.tiktok_reason = "skipped", problem
        return
    if not video.mp4_key:
        run.tiktok_state, run.tiktok_reason = "failed", "Bản TikTok chưa có MP4"
        return
    post = Publication(
        video_id=video.id,
        platform="tiktok",
        status="pending",
        created_by_id=page.owner_id,
        affiliate_account_id=page.tiktok_account_id,
        publish_mode="draft",
    )
    db.add(post)
    db.flush()
    db.add(
        Job(
            video_id=video.id,
            kind="tiktok_publish",
            status="queued",
            created_by_id=page.owner_id,
            publication_id=post.id,
        )
    )
    run.tiktok_state, run.tiktok_publication_id, run.tiktok_reason = "sent", post.id, None
    db.flush()


# --- Reading ---


def runs_of(db: DbSession, topic_id: int | None = None, day: date | None = None) -> list[AutoRun]:
    query = select(AutoRun).where(AutoRun.role == "facebook")
    if topic_id is not None:
        query = query.where(AutoRun.fanpage_id.in_(select(Fanpage.id).where(Fanpage.knowledge_topic_id == topic_id)))
    if day is not None:
        query = query.where(AutoRun.day == day)
    return list(db.scalars(query.order_by(AutoRun.day.desc(), AutoRun.fanpage_id, AutoRun.id)))


def payload(db: DbSession, run: AutoRun, user_id: int) -> dict:
    page = db.get(Fanpage, run.fanpage_id)
    video = db.get(Video, run.video_id) if run.video_id else None
    child = _tiktok_child(db, run)
    post = db.get(Publication, run.publication_id) if run.publication_id else None
    tiktok_problem = tiktok_account_problem(db, page) if page.owner_id else "Page chưa có chủ sở hữu"
    music = video.music_name if video is not None else None
    return {
        "id": run.id,
        "day": run.day.isoformat(),
        "fanpage": {"id": page.id, "name": page.name},
        "can_decide": page.owner_id == user_id,
        "plan_item_id": run.plan_item_id,
        "idea_topic": run.idea_topic,
        "status": run.status,
        "stage": run.stage,
        "reason": run.reason,
        "banned": run.banned,
        "video": None
        if video is None
        else {
            "id": video.id,
            "mp4_url": f"/api/videos/{video.id}/video.mp4?v={_version(video.mp4_key)}" if video.mp4_key else None,
            "voice_id": (video.options or {}).get("voice_id", ""),
            "music": music,
        },
        "tiktok_video_id": child.video_id if child is not None else None,
        # Before approval: whether a draft would go to TikTok, and why not; after: what happened to it.
        "tiktok_ready": tiktok_problem is None,
        "tiktok_problem": tiktok_problem,
        "tiktok_state": run.tiktok_state,
        "tiktok_reason": run.tiktok_reason,
        "post_at": (post.scheduled_at or post.published_at).isoformat()
        if post and (post.scheduled_at or post.published_at)
        else None,
        "decided_at": run.decided_at.isoformat() if run.decided_at else None,
    }
