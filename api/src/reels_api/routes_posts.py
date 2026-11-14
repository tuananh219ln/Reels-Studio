"""The "Bài đăng" board (posts_board.py): every rendered video and where it stands on Facebook, TikTok and YouTube,
with the links of posts made by hand pasted in (post_links.py); and the reels on Facebook for the calendar. A video
is reviewed and posted from its own page; here a member records posts made elsewhere, asks for a post's numbers to
be read again, and takes a recorded post out."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from . import analytics, metrics, post_links, posts_board
from .db import get_db
from .errors import ApiError
from .models import Channel, Job, PostMetricSnapshot, Publication, Session, User, Video
from .routes_videos import invalid
from .sessions import current_member, now
from .videos import (
    active_job,
    is_published,
    live_at,
    publication_payload,
    split_scenes,
    thumbnail_url,
    video_name,
)

router = APIRouter(prefix="/api/posts")


def _attempt(db: DbSession, post: Publication) -> dict | None:
    """Where a post not on Facebook yet stands: its video's last publish job is still to run ("working"), or failed
    ("failed", with the job "Thử lại" sends again and its reason). None for a post past that."""
    if post.status != "pending":
        return None
    job = db.scalar(
        select(Job).where(Job.video_id == post.video_id, Job.kind == "publish").order_by(Job.id.desc()).limit(1)
    )
    if job is None or job.status != "failed":
        return {"state": "working", "job_id": None, "error": None}
    return {"state": "failed", "job_id": job.id, "error": job.error}


def _payload(db: DbSession, video: Video, post: Publication, by_page: dict) -> dict:
    title, _ = split_scenes(db, video)
    return {
        **publication_payload(post, by_page),
        # Whose it is: "Của tôi" keeps the posts a member made or that are on a Page they own.
        "created_by_id": post.created_by_id,
        "fanpage_owner_id": post.fanpage.owner_id if post.fanpage else None,
        "video_id": video.id,
        # The video's topic group, for "Lịch đăng" of Kho kiến thức.
        "knowledge_topic_id": video.knowledge_topic_id,
        "title": video_name(video, title),
        "thumbnail_url": thumbnail_url(video),
        "busy": active_job(db, video.id) is not None,
        "attempt": _attempt(db, post),
    }


@router.get("")
def list_posts(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(Video, Publication).join(Publication).where(Publication.platform == "facebook"))
    by_page = analytics.medians(db)
    return [
        _payload(db, video, post, by_page)
        for video, post in sorted(rows, key=lambda row: live_at(row[1]), reverse=True)
    ]


@router.get("/kpis")
def weekly_kpis(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """The KPI strip of "Bài đăng": this week and last, Monday to Sunday in Vietnam time, from the 48-hour numbers."""
    return analytics.kpis(db)


@router.post("/freshen")
def freshen(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Opening "Bài đăng": the worker reads the followed posts not read lately. The request never calls Facebook."""
    asked = metrics.ask_if_stale(db)
    db.commit()
    return {"asked": asked}


@router.post("/refresh")
def refresh_topic(
    knowledge_topic_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Cập nhật view" of a topic group: the worker reads the numbers of its posts in its next round. The request never
    calls Facebook."""
    asked = metrics.ask_for_topic(db, knowledge_topic_id)
    db.commit()
    return {"asked": asked}


@router.post("/{post_id}/comment")
def request_comment(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Bình luận ngay" / "Cập nhật bình luận": the worker writes the affiliate comment, or edits the one it wrote, in
    its next round. The request itself never calls Facebook."""
    post = db.get(Publication, post_id, with_for_update=True)
    # An article's post is handled on its own page (/api/articles).
    if post is None or post.video_id is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    if post.platform != "facebook" or post.remote_id is None or not is_published(post):
        raise ApiError(409, "post_not_live", "Chỉ bình luận được dưới bài đã lên Facebook")
    if db.get(Video, post.video_id).manual_comment:
        raise ApiError(
            409,
            "manual_comment",
            "Video đã đánh dấu dán link tay nên app không bình luận; bỏ đánh dấu ở Affiliate trước",
        )
    post.comment_requested_at = now()
    db.commit()
    return _payload(db, db.get(Video, post.video_id), post, analytics.medians(db))


@router.post("/{post_id}/metrics")
def refresh_metrics(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Cập nhật view": the worker reads the post's numbers in its next round, within seconds. The request
    itself never calls Facebook."""
    post = db.get(Publication, post_id, with_for_update=True)
    # An article's post is handled on its own page (/api/articles).
    if post is None or post.video_id is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    if post.platform != "facebook" or post.remote_id is None or not is_published(post):
        raise ApiError(409, "post_not_measurable", "Chỉ cập nhật view được cho bài đã đăng lên Facebook")
    post.metrics_requested_at = now()
    db.commit()
    return _payload(db, db.get(Video, post.video_id), post, analytics.medians(db))


# --- The board ("Bài đăng", docs/decisions/2026-11-14-posts-board.md) ---
# Declared before "/{post_id}", whose int path would otherwise answer "/board" with a 422.


@router.get("/board")
def get_board(
    tab: str = "all",
    platform: str | None = None,
    channel: list[str] = Query(default=[]),
    missing_on: str | None = None,
    owner: str = "team",
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str | None = None,
    q: str = "",
    cursor: int = 0,
    limit: int = posts_board.PAGE_SIZE,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """One row per rendered video, a cell per platform, the tabs' counts under the same filters."""
    if tab not in posts_board.TABS:
        raise invalid("Tab không hợp lệ")
    for value in (platform, missing_on):
        if value is not None and value not in posts_board.PLATFORMS:
            raise invalid("Nền tảng không hợp lệ")
    if sort is not None and sort not in posts_board.SORTS:
        raise invalid("Cách sắp xếp không hợp lệ")
    filters = posts_board.Filters(
        tab=tab,
        platform=platform,
        channels=set(channel),
        missing_on=missing_on,
        owner_id=me.user_id if owner == "me" else None,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        query=q.strip(),
    )
    return posts_board.board(db, filters, max(cursor, 0), min(max(limit, 1), posts_board.MAX_PAGE_SIZE))


@router.get("/videos/{video_id}")
def video_posts(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """A video's posts on every platform, for its opened row on the board."""
    video = db.get(Video, video_id)
    if video is None:
        raise ApiError(404, "video_not_found", "Không tìm thấy video")
    by_page = analytics.medians(db)
    return posts_board.video_posts(db, video, lambda post: _payload(db, video, post, by_page))


class PendingBody(BaseModel):
    video_id: int
    platform: str


@router.post("/pending")
def mark_pending(body: PendingBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Tải MP4" in a TikTok or YouTube cell: the video waits for its link there ("Chờ dán link"), unless it is
    already out or waiting there."""
    if body.platform not in ("tiktok", "youtube"):
        raise invalid("Chỉ TikTok và YouTube chờ dán link")
    video = db.get(Video, body.video_id, with_for_update=True)
    if video is None:
        raise ApiError(404, "video_not_found", "Không tìm thấy video")
    if not video.mp4_key:
        raise invalid("Video chưa render MP4 để đăng")
    already = db.scalar(
        select(Publication.id).where(
            Publication.video_id == video.id,
            Publication.platform == body.platform,
            Publication.status.in_(("pending_link", "pending", "scheduled", "published")),
        )
    )
    if already is None:
        db.add(
            Publication(
                video_id=video.id,
                platform=body.platform,
                status="pending_link",
                source="manual_link",
                mp4_downloaded_at=now(),
                created_by_id=me.user_id,
            )
        )
    db.commit()
    return {"created": already is None}


class PreviewBody(BaseModel):
    urls: list[str]
    video_id: int | None = None  # opened from a cell: the video is fixed, no matching
    platform: str | None = None


def _clean_urls(urls: list[str]) -> list[str]:
    cleaned = [url.strip() for url in urls if url.strip()]
    if not cleaned:
        raise invalid("Hãy dán ít nhất một link")
    if len(cleaned) > post_links.MAX_LINKS:
        raise invalid(f"Mỗi lần dán tối đa {post_links.MAX_LINKS} link")
    return cleaned


def _fetch(raw: str, client: httpx.Client) -> tuple:
    """The network part of a preview (a short link's redirect, oEmbed), run in parallel; no database here."""
    try:
        link = post_links.read(raw, client)
    except post_links.LinkError as err:
        return None, None, err
    try:
        return link, post_links.oembed(link, client), None
    except post_links.LinkError as err:
        return link, None, err


def _preview_row(db: DbSession, raw: str, fetched: tuple, context: dict) -> dict:
    link, meta, error = fetched
    at = context["at"]
    row = {
        "input": raw,
        "url": link.url if link else None,
        "platform": link.platform if link else None,
        "external_id": link.external_id if link else None,
        "channel": None,
        "channel_options": [],
        "title": meta.title if meta else None,
        "thumbnail_url": meta.thumbnail_url if meta else None,
        "published_at": (meta.published_at if meta and meta.published_at else at).isoformat(),
        "published_at_source": "api" if meta and meta.published_at else "user",
        "video": None,
        "score": None,
        "suggestions": [],
        "existing_video": None,
        "result": "invalid",
        "message": "Link không hợp lệ",
    }
    if link is None:
        row["result"], row["message"] = error.code, error.message
        return row
    if context["platform"] and link.platform != context["platform"]:
        row["message"] = f"Đây không phải link {post_links.PLATFORM_LABELS[context['platform']]}"
        return row
    if (link.platform, link.external_id) in context["seen"]:
        row["result"], row["message"] = "duplicate", "Trùng với link ở dòng trên"
        return row
    context["seen"].add((link.platform, link.external_id))
    existing = post_links.existing_post(db, link)
    if existing is not None:
        row["result"], row["message"] = "duplicate", "Đã có trong hệ thống"
        if existing.video_id is not None:
            row["existing_video"] = post_links.video_ref(db, db.get(Video, existing.video_id))
        return row
    if error is not None:
        row["result"], row["message"] = error.code, error.message
        return row
    if link.platform == "facebook":
        pages = context["pages"]
        row["channel_options"] = [{"kind": "fanpage", "id": page.id, "name": page.name} for page in pages]
        if not pages:
            row["result"], row["message"] = "unknown_channel", "Bạn chưa có Page nào để ghi bài Facebook"
            return row
        if len(pages) == 1:
            row["channel"] = row["channel_options"][0]
    else:
        found = post_links.find_channel(db, link, meta)
        if found is None:
            row["result"], row["message"] = "unknown_channel", "Kênh chưa khai báo"
            return row
        row["channel"] = found.payload()
    if context["video"] is not None:
        row["video"] = post_links.video_ref(db, context["video"])
    elif meta is not None:
        match = post_links.match_video(db, meta.title, meta.published_at or at, meta.duration)
        row["score"] = round(match.score * 100) if match.score is not None else None
        row["suggestions"] = [post_links.video_ref(db, video, value) for video, value in match.suggestions]
        if match.video is not None:
            row["video"] = post_links.video_ref(db, match.video, match.score)
    ready = row["video"] is not None and row["channel"] is not None
    row["result"] = "matched" if ready else "choose"
    if ready:
        row["message"] = f"Khớp {row['score']}%" if row["score"] is not None else "Sẵn sàng"
    else:
        row["message"] = "Cần chọn tay"
    return row


@router.post("/links/preview")
def preview_links(body: PreviewBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """What each pasted link is, its channel, the video it matches and whether it can be saved. Saves nothing."""
    urls = _clean_urls(body.urls)
    video = None
    if body.video_id is not None:
        video = db.get(Video, body.video_id)
        if video is None:
            raise ApiError(404, "video_not_found", "Không tìm thấy video")
    if body.platform is not None and body.platform not in posts_board.PLATFORMS:
        raise invalid("Nền tảng không hợp lệ")
    with httpx.Client(timeout=post_links.TIMEOUT) as client, ThreadPoolExecutor(max_workers=8) as pool:
        fetched = list(pool.map(lambda raw: _fetch(raw, client), urls))
    context = {
        "at": now(),
        "platform": body.platform,
        "video": video,
        "pages": post_links.my_pages(db, me.user_id),
        "seen": set(),
    }
    return {"items": [_preview_row(db, raw, row, context) for raw, row in zip(urls, fetched, strict=True)]}


class LinkItem(BaseModel):
    url: str
    video_id: int
    # The post's channel: a Page for Facebook, a TikTok account, a YouTube channel (`channels`).
    channel_id: int
    published_at: datetime | None = None
    # The member typed the time: a reading never replaces it with the platform's.
    published_at_edited: bool = False


class SaveLinksBody(BaseModel):
    items: list[LinkItem]


def _channel_fields(db: DbSession, link: post_links.Link, channel_id: int, me: Session) -> dict:
    if link.platform == "facebook":
        if channel_id not in {page.id for page in post_links.my_pages(db, me.user_id)}:
            raise invalid("Chỉ ghi được bài Facebook trên Page của chính bạn")
        return {"fanpage_id": channel_id, "remote_id": link.external_id}
    if link.platform == "tiktok":
        handles = dict(post_links.tiktok_accounts(db))
        account = next((account for account in handles if account.id == channel_id), None)
        if account is None:
            raise invalid("Kênh TikTok chưa khai báo")
        if handles[account] and link.handle and handles[account] != link.handle:
            raise invalid("Link không thuộc kênh TikTok đã chọn")
        return {"affiliate_account_id": channel_id}
    channel = db.get(Channel, channel_id)
    if channel is None or channel.platform != "youtube":
        raise invalid("Kênh YouTube chưa khai báo")
    return {"channel_id": channel_id}


@router.post("/links")
def save_links(body: SaveLinksBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Lưu n link": each post recorded (a video waiting for its link there gets it), or nothing when a line is
    wrong. A Facebook post is read by the worker at once; TikTok and YouTube numbers come later."""
    if not body.items:
        raise invalid("Chưa có link nào để lưu")
    if len(body.items) > post_links.MAX_LINKS:
        raise invalid(f"Mỗi lần lưu tối đa {post_links.MAX_LINKS} link")
    at = now()
    try:
        saved = _save_lines(db, body.items, at, me)
        db.commit()
    except ApiError:
        db.rollback()  # a wrong line saves nothing, not even the lines before it
        raise
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "post_exists", "Có link vừa được người khác lưu, hãy dán lại") from None
    return {"saved": len(saved), "post_ids": [post.id for post in saved]}


def _save_lines(db: DbSession, items: list[LinkItem], at: datetime, me: Session) -> list[Publication]:
    saved: list[Publication] = []
    seen: set[tuple[str, str]] = set()
    for number, item in enumerate(items, start=1):
        try:
            link = post_links.parse(item.url)
        except post_links.LinkError as err:
            raise invalid(f"Dòng {number}: {err.message}") from None
        if (link.platform, link.external_id) in seen or post_links.existing_post(db, link) is not None:
            raise ApiError(409, "post_exists", f"Dòng {number}: link đã có trong hệ thống")
        seen.add((link.platform, link.external_id))
        video = db.get(Video, item.video_id)
        if video is None:
            raise ApiError(404, "video_not_found", f"Dòng {number}: không tìm thấy video")
        published_at = item.published_at or at
        if published_at.tzinfo is None or published_at > at + timedelta(minutes=5):
            raise invalid(f"Dòng {number}: giờ đăng không hợp lệ")
        try:
            fields = _channel_fields(db, link, item.channel_id, me)
        except ApiError as err:
            raise invalid(f"Dòng {number}: {err.message}") from None
        post = db.scalar(
            select(Publication)
            .where(
                Publication.video_id == video.id,
                Publication.platform == link.platform,
                Publication.status == "pending_link",
            )
            .with_for_update()
        )
        if post is None:
            post = Publication(video_id=video.id, platform=link.platform, created_by_id=me.user_id)
            db.add(post)
        post.status, post.source = "published", "manual_link"
        post.external_id, post.post_url = link.external_id, link.url
        post.published_at = published_at
        post.published_at_source = "user" if item.published_at_edited else None
        post.remote_mp4_key = video.mp4_key
        for name, value in fields.items():
            setattr(post, name, value)
        if link.platform in ("facebook", "youtube"):
            # The first reading at once (§3.1); a YouTube one only runs with the team's key.
            post.metrics_requested_at = at
        db.flush()
        saved.append(post)
    return saved


class PostChange(BaseModel):
    status: str | None = None  # "cancelled": "Hủy chờ" on a post waiting for its link
    url: str | None = None  # "Sửa link" on a post recorded with its link
    published_at: datetime | None = None


@router.patch("/{post_id}")
def change_post(
    post_id: int, body: PostChange, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    post = db.get(Publication, post_id, with_for_update=True)
    if post is None or post.video_id is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    if body.status is not None:
        if body.status != "cancelled" or post.status != "pending_link":
            raise invalid("Chỉ hủy được bài đang chờ dán link")
        post.status, post.closed_at, post.closed_by_id = "cancelled", now(), me.user_id
    if (body.url is not None or body.published_at is not None) and (
        post.source != "manual_link" or post.status != "published"
    ):
        raise invalid("Chỉ sửa được bài đã ghi bằng link")
    if body.url is not None:
        try:
            link = post_links.parse(body.url)
        except post_links.LinkError as err:
            raise invalid(err.message) from None
        if link.platform != post.platform:
            raise invalid(f"Đây không phải link {post_links.PLATFORM_LABELS.get(post.platform, post.platform)}")
        existing = post_links.existing_post(db, link)
        if existing is not None and existing.id != post.id:
            raise ApiError(409, "post_exists", "Link đã có trong hệ thống")
        post.external_id, post.post_url = link.external_id, link.url
        if post.platform == "facebook":
            post.remote_id, post.metrics_requested_at = link.external_id, now()
    if body.published_at is not None:
        if body.published_at.tzinfo is None or body.published_at > now() + timedelta(minutes=5):
            raise invalid("Giờ đăng không hợp lệ")
        post.published_at, post.published_at_source = body.published_at, "user"
        # The readings' ages follow the new time; marks already set stay (§7).
        for snapshot in db.scalars(select(PostMetricSnapshot).where(PostMetricSnapshot.publication_id == post.id)):
            snapshot.hours_since_publish = metrics.hours_since(body.published_at, snapshot.captured_at)
    db.commit()
    return {"ok": True}


REFRESH_EVERY = timedelta(minutes=5)
MAX_REFRESH = 200


class RefreshBody(BaseModel):
    video_ids: list[int]


@router.post("/metrics/refresh")
def refresh_views(body: RefreshBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Cập nhật view" on the board: the worker reads the out posts of the videos shown (at most 200), in its next
    rounds. Once per 5 minutes per member. The request never calls a platform."""
    user = db.get(User, me.user_id, with_for_update=True)
    at = now()
    if user.views_refreshed_at is not None and at - user.views_refreshed_at < REFRESH_EVERY:
        wait = REFRESH_EVERY - (at - user.views_refreshed_at)
        minutes = max(1, -(-int(wait.total_seconds()) // 60))
        raise ApiError(429, "refresh_too_soon", f"Vừa cập nhật view, thử lại sau {minutes} phút")
    posts = (
        db.scalars(
            select(Publication)
            .where(
                Publication.video_id.in_(body.video_ids[:MAX_REFRESH]),
                metrics.readable(at),
            )
            .order_by(Publication.id.desc())
            .limit(MAX_REFRESH)
        ).all()
        if body.video_ids
        else []
    )
    for post in posts:
        post.metrics_requested_at = at
    user.views_refreshed_at = at
    db.commit()
    return {"asked": len(posts)}


@router.delete("/{post_id}")
def remove_post(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Gỡ": a post recorded with its link (or waiting for it) leaves the app; the post on the platform stays."""
    post = db.get(Publication, post_id)
    if post is None or post.video_id is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    if post.source != "manual_link":
        raise invalid("Chỉ gỡ được bài ghi bằng link")
    if post.created_by_id != me.user_id:
        raise ApiError(403, "not_post_author", "Chỉ người ghi bài này mới gỡ được")
    db.delete(post)
    db.commit()
    return {"ok": True}


@router.get("/{post_id}")
def get_post(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Read one managed reel with the same actions and metrics as the posts list."""
    post = db.get(Publication, post_id)
    if post is None or post.video_id is None or post.platform != "facebook":
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    return _payload(db, db.get(Video, post.video_id), post, analytics.medians(db))
