"""'Phân tích đối thủ': a member pastes a competitor's Facebook link, their own Chrome reads its Reels grid through the
team's extension (never the server: Facebook shows views only to a signed-in browser), and the numbers are summed
here in code, so the member's Claude analyses topics and pains through MCP without adding anything up itself.

docs/decisions/2026-11-17-competitor-analyzer.md; the extension's side is extension/facebook-reels.js.
"""

import re
import statistics
import unicodedata
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from .errors import ApiError
from .models import Competitor, CompetitorComment, CompetitorReport, CompetitorScan, CompetitorVideo, User
from .sessions import now

MAX_VIDEOS_DEFAULT = 500
MAX_VIDEOS_LIMIT = 2000
# M3: the most viewed videos whose own page is opened for caption, sound and reactions (4–8 s apart).
CAPTIONS_TOP_DEFAULT = 30
CAPTIONS_TOP_LIMIT = 100
CAPTION_LIMIT = 5000
# M4: of those, the most viewed whose comments are sampled, and how many comments each.
COMMENTS_TOP_DEFAULT = 10
COMMENTS_TOP_LIMIT = 30
COMMENTS_PER_VIDEO = 30
COMMENT_LIMIT = 2000
# A saved report: what an assistant may write, kept well under the MCP request limit (128 KB).
REPORT_MARKDOWN_LIMIT = 60_000
REPORT_LIST_LIMIT = 30
# A batch the extension sends: 50 at a time, so a closed tab loses little.
BATCH_LIMIT = 100
# A running scan whose page has been silent this long was closed mid-way: it is claimed again (resumed).
STALLED_AFTER = timedelta(minutes=3)
# The page says the extension is there every time it polls (about once a minute when idle).
SCANNER_ONLINE_FOR = timedelta(minutes=3)

FACEBOOK_HOSTS = {"facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com", "mbasic.facebook.com"}
# First path parts that are Facebook's own pages, never a Page's or person's name.
RESERVED = {
    "watch",
    "reel",
    "reels",
    "groups",
    "share",
    "events",
    "marketplace",
    "gaming",
    "login",
    "login.php",
    "story.php",
    "permalink.php",
    "photo",
    "photo.php",
    "photos",
    "video.php",
    "videos",
    "hashtag",
    "help",
    "settings",
    "search",
    "home.php",
    "messages",
    "notifications",
    "friends",
    "stories",
    "live",
    "ads",
    "business",
    "privacy",
    "policies",
}
USERNAME = re.compile(r"^[A-Za-z0-9.\-_]{2,100}$")
NUMERIC_ID = re.compile(r"^\d{5,30}$")
TABS = {"reels", "videos", "about", "photos", "posts", "followers", "mentions", "reviews", "community"}

BAD_LINK = "Link không phải trang Facebook (Page hoặc trang cá nhân), ví dụ facebook.com/tenpage"


def parse_url(raw: str) -> dict:
    """A competitor's link, canonical: `facebook.com/<name>` and its /reels, /videos tabs become
    https://www.facebook.com/<name>; `profile.php?id=` and `/people/<name>/<id>` become profile.php?id=<id>.
    Every other query part is dropped. Returns {fb_url, fb_id, kind, reels_url}."""
    text = (raw or "").strip()
    if not text:
        raise ApiError(422, "bad_competitor_url", BAD_LINK)
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or host not in FACEBOOK_HOSTS:
        raise ApiError(422, "bad_competitor_url", BAD_LINK)
    segments = [segment for segment in parts.path.split("/") if segment]
    if segments and segments[0] == "pg":  # the old /pg/<name>/ address of a Page
        segments = segments[1:]
    if segments[:1] == ["profile.php"]:
        ids = parse_qs(parts.query).get("id", [])
        if not ids or not NUMERIC_ID.match(ids[0]):
            raise ApiError(422, "bad_competitor_url", BAD_LINK)
        return _numeric(ids[0])
    if len(segments) >= 3 and segments[0] == "people" and NUMERIC_ID.match(segments[2]):
        return _numeric(segments[2])
    if not segments:
        raise ApiError(422, "bad_competitor_url", BAD_LINK)
    name = segments[0]
    if (
        name.lower() in RESERVED
        or not USERNAME.match(name)
        or len(segments) > 2
        or (len(segments) == 2 and segments[1] not in TABS)
    ):
        raise ApiError(422, "bad_competitor_url", BAD_LINK)
    url = f"https://www.facebook.com/{name}"
    return {"fb_url": url, "fb_id": None, "kind": "page", "reels_url": url + "/reels/"}


def _numeric(fb_id: str) -> dict:
    url = f"https://www.facebook.com/profile.php?id={fb_id}"
    return {"fb_url": url, "fb_id": fb_id, "kind": "profile", "reels_url": url + "&sk=reels_tab"}


# "4,5M", "288K", "7,6 N", "1,2 Tr lượt xem", "12.345", "980": Facebook writes views in the reader's locale, so "." and
# "," may each be the decimal mark. Vietnamese uses N (nghìn) and Tr (triệu).
VIEWS = re.compile(r"^(?P<number>\d[\d.,\s]*?)\s*(?P<unit>k|n|nghìn|ngàn|m|tr|triệu|b|tỷ|ty)?\.?$", re.IGNORECASE)
UNITS = {
    "k": 1_000,
    "n": 1_000,
    "nghìn": 1_000,
    "ngàn": 1_000,
    "m": 1_000_000,
    "tr": 1_000_000,
    "triệu": 1_000_000,
    "b": 1_000_000_000,
    "tỷ": 1_000_000_000,
    "ty": 1_000_000_000,
}
NOISE = re.compile(r"(lượt xem|lượt phát|views?|plays?)", re.IGNORECASE)


def parse_views(raw: str | None) -> int | None:
    """The number a grid shows, as an integer; None when it is not one."""
    if not raw:
        return None
    text = NOISE.sub("", unicodedata.normalize("NFC", raw)).replace("\u00a0", " ").strip()
    found = VIEWS.match(text)
    if not found:
        return None
    number = found["number"].replace(" ", "")
    unit = (found["unit"] or "").lower()
    if not unit and re.fullmatch(r"\d{1,3}([.,]\d{3})+", number):
        number = re.sub(r"[.,]", "", number)  # "12.345" or "1,234,567": thousands separators
    else:
        marks = re.findall(r"[.,]", number)
        if len(marks) > 1:
            return None
        number = number.replace(",", ".")
    try:
        value = Decimal(number) * UNITS.get(unit, 1)
    except InvalidOperation:
        return None
    return int(value.to_integral_value())


def scanner_online(user: User) -> bool:
    seen = user.competitor_scanner_at
    return seen is not None and now() - seen < SCANNER_ONLINE_FOR


def start_scan(
    db: DbSession,
    user_id: int,
    url: str,
    max_videos: int = MAX_VIDEOS_DEFAULT,
    captions_top: int = CAPTIONS_TOP_DEFAULT,
    comments_top: int = COMMENTS_TOP_DEFAULT,
) -> CompetitorScan:
    """A queued scan of the competitor at `url` (made on first use). One waiting or running scan per competitor: a
    second request answers the one already there."""
    parsed = parse_url(url)
    competitor = db.scalar(
        select(Competitor).where(Competitor.owner_id == user_id, Competitor.fb_url == parsed["fb_url"])
    )
    if competitor is None:
        competitor = Competitor(owner_id=user_id, fb_url=parsed["fb_url"], fb_id=parsed["fb_id"], kind=parsed["kind"])
        db.add(competitor)
        db.flush()
    active = db.scalar(
        select(CompetitorScan).where(
            CompetitorScan.competitor_id == competitor.id, CompetitorScan.status.in_(("queued", "running"))
        )
    )
    if active is not None:
        return active
    scan = CompetitorScan(
        competitor_id=competitor.id,
        owner_id=user_id,
        status="queued",
        scope={
            "reels": True,
            "videos": False,
            "max_videos": max(1, min(max_videos, MAX_VIDEOS_LIMIT)),
            "fetch_captions_top_n": max(0, min(captions_top, CAPTIONS_TOP_LIMIT)),
            "fetch_comments_top_n": max(0, min(comments_top, COMMENTS_TOP_LIMIT, captions_top)),
        },
    )
    db.add(scan)
    db.flush()
    return scan


def own_scan(db: DbSession, scan_id: int, user_id: int, lock: bool = False) -> CompetitorScan:
    query = select(CompetitorScan).where(CompetitorScan.id == scan_id, CompetitorScan.owner_id == user_id)
    scan = db.scalar(query.with_for_update() if lock else query)
    if scan is None:
        raise ApiError(404, "scan_not_found", "Không tìm thấy lượt quét này")
    return scan


def own_competitor(db: DbSession, competitor_id: int, user_id: int) -> Competitor:
    competitor = db.get(Competitor, competitor_id)
    if competitor is None or competitor.owner_id != user_id:
        raise ApiError(404, "competitor_not_found", "Không tìm thấy đối thủ này")
    return competitor


def claim(db: DbSession, user: User) -> CompetitorScan | None:
    """The next scan the member's open page should run, now marked running: a running one gone silent first (the
    page was closed mid-way; it resumes), else the oldest queued one. None while one is genuinely running: one scan
    at a time per member, so one Facebook account is never read twice at once."""
    # The member's row is the lock: two tabs claiming at once take turns, so only one gets a scan.
    db.execute(select(User.id).where(User.id == user.id).with_for_update())
    user.competitor_scanner_at = now()
    mine = select(CompetitorScan).where(CompetitorScan.owner_id == user.id)
    running = db.scalars(mine.where(CompetitorScan.status == "running")).all()
    stalled = [scan for scan in running if scan.heartbeat_at is None or now() - scan.heartbeat_at > STALLED_AFTER]
    if len(stalled) < len(running):
        return None
    scan = stalled[0] if stalled else None
    if scan is None:
        scan = db.scalar(mine.where(CompetitorScan.status == "queued").order_by(CompetitorScan.id).limit(1))
    if scan is None:
        return None
    scan.status = "running"
    scan.started_at = scan.started_at or now()
    scan.heartbeat_at = now()
    scan.error = None
    return scan


def ensure_running(scan: CompetitorScan) -> None:
    if scan.status != "running":
        raise ApiError(409, "scan_not_running", "Lượt quét này không còn chạy")


def add_videos(db: DbSession, scan: CompetitorScan, videos: list[dict]) -> int:
    """Saves a batch from the grid; a video seen again (a resumed scan scrolls from the top) is updated, never
    doubled. Returns the scan's number of videos."""
    ensure_running(scan)
    rows = {}
    for video in videos:
        raw = (video.get("views_raw") or "").strip()[:60] or None
        rows[video["fb_video_id"]] = {
            "scan_id": scan.id,
            "fb_video_id": video["fb_video_id"],
            "url": video["url"],
            "type": video.get("type", "reel"),
            "views": parse_views(raw),
            "views_raw": raw,
            "position": video.get("position"),
        }
    if rows:
        statement = insert(CompetitorVideo).values(list(rows.values()))
        db.execute(
            statement.on_conflict_do_update(
                constraint="uq_competitor_videos_scan_video",
                set_={
                    "url": statement.excluded.url,
                    # A later reading without a number keeps the one already read.
                    "views": func.coalesce(statement.excluded.views, CompetitorVideo.views),
                    "views_raw": func.coalesce(statement.excluded.views_raw, CompetitorVideo.views_raw),
                    "position": func.coalesce(statement.excluded.position, CompetitorVideo.position),
                },
            )
        )
    scan.videos_found = db.scalar(select(func.count()).where(CompetitorVideo.scan_id == scan.id)) or 0
    scan.heartbeat_at = now()
    return scan.videos_found


def captions_top(scan: CompetitorScan) -> int:
    return (scan.scope or {}).get("fetch_captions_top_n", CAPTIONS_TOP_DEFAULT)


def comments_top(scan: CompetitorScan) -> int:
    return (scan.scope or {}).get("fetch_comments_top_n", 0)


def enrich_targets(db: DbSession, scan: CompetitorScan) -> list[str]:
    """The most viewed videos of a running scan whose own page the extension opens next (M3); the first
    comments_top(scan) of them also have their comments sampled (M4)."""
    ensure_running(scan)
    scan.heartbeat_at = now()
    limit = captions_top(scan)
    if not limit:
        return []
    return list(
        db.scalars(
            select(CompetitorVideo.fb_video_id)
            .where(CompetitorVideo.scan_id == scan.id, CompetitorVideo.views.is_not(None))
            .order_by(CompetitorVideo.views.desc(), CompetitorVideo.id)
            .limit(limit)
        )
    )


def add_details(db: DbSession, scan: CompetitorScan, details: list[dict]) -> int:
    """What a reel's own page showed: caption, sound, length and the counts as written ("1,2K"). Only videos the scan
    already has are changed; a field the page did not show keeps what was read before. Returns how many changed."""
    ensure_running(scan)
    changed = 0
    for detail in details:
        video = db.scalar(
            select(CompetitorVideo).where(
                CompetitorVideo.scan_id == scan.id, CompetitorVideo.fb_video_id == detail["fb_video_id"]
            )
        )
        if video is None:
            continue
        caption = (detail.get("caption") or "").strip()
        if caption:
            video.caption = caption[:CAPTION_LIMIT]
        audio = (detail.get("audio_name") or "").strip()
        if audio:
            video.audio_name = audio[:300]
        if detail.get("duration_s"):
            video.duration_s = detail["duration_s"]
        for field in ("reactions", "comments", "shares"):
            value = parse_views(detail.get(f"{field}_raw"))
            if value is not None:
                setattr(video, field, value)
        samples = [sample for sample in detail.get("comment_samples") or [] if (sample.get("text") or "").strip()][
            :COMMENTS_PER_VIDEO
        ]
        if samples:
            db.execute(delete(CompetitorComment).where(CompetitorComment.video_id == video.id))
            for position, sample in enumerate(samples):
                db.add(
                    CompetitorComment(
                        video_id=video.id,
                        position=position,
                        text=sample["text"].strip()[:COMMENT_LIMIT],
                        like_count=parse_views(sample.get("likes_raw")),
                    )
                )
        changed += 1
    scan.heartbeat_at = now()
    return changed


def finish(
    db: DbSession, scan: CompetitorScan, status: str, error: str | None, name: str | None, followers: str | None
) -> None:
    """The page's last word: done, partial (stopped early: a checkpoint, the window closed, the time limit) or failed."""
    ensure_running(scan)
    scan.status = status
    scan.error = (error or "").strip()[:500] or None
    scan.finished_at = now()
    scan.heartbeat_at = now()
    if name and name.strip():
        scan.competitor.name = name.strip()[:200]
    if followers:
        scan.competitor.followers = parse_views(followers)


def resume(scan: CompetitorScan) -> None:
    """ "Tiếp tục": a stopped scan is queued again; its videos stay and are updated as the grid is read again."""
    if scan.status not in ("partial", "failed"):
        raise ApiError(409, "scan_not_resumable", "Chỉ tiếp tục được lượt quét dừng giữa chừng hoặc bị lỗi")
    scan.status = "queued"
    scan.finished_at = None
    scan.error = None


def videos_of(db: DbSession, scan_id: int) -> list[CompetitorVideo]:
    return db.scalars(
        select(CompetitorVideo)
        .where(CompetitorVideo.scan_id == scan_id)
        .order_by(CompetitorVideo.views.desc().nulls_last(), CompetitorVideo.position.nulls_last(), CompetitorVideo.id)
    ).all()


BUCKETS = (
    ("≥1M", 1_000_000, None),
    ("100K–1M", 100_000, 1_000_000),
    ("10K–100K", 10_000, 100_000),
    ("<10K", 0, 10_000),
)


def stats(db: DbSession, scan: CompetitorScan) -> dict:
    """The scan's numbers, in code so an assistant never adds them up itself."""
    videos = videos_of(db, scan.id)
    views = [video.views for video in videos if video.views is not None]
    total = sum(views)
    top10 = sum(views[:10])  # videos_of sorts by views, highest first
    dated = sorted(video.posted_at for video in videos if video.posted_at is not None)
    per_week = None
    if len(dated) >= 2:
        weeks = max((dated[-1] - dated[0]).days / 7, 1)
        per_week = round(len(dated) / weeks, 1)
    return {
        "scan_id": scan.id,
        "status": scan.status,
        "videos": len(videos),
        "videos_with_views": len(views),
        "total_views": total,
        "median_views": int(statistics.median(views)) if views else None,
        "mean_views": round(total / len(views)) if views else None,
        "max_views": views[0] if views else None,
        "buckets": [
            {
                "label": label,
                "videos": sum(1 for value in views if value >= low and (high is None or value < high)),
                "views": sum(value for value in views if value >= low and (high is None or value < high)),
            }
            for label, low, high in BUCKETS
        ],
        "top10_views": top10,
        "top10_share": round(top10 / total, 4) if total else None,
        "videos_per_week": per_week,
        "dated_videos": len(dated),
        "limits": _limits(scan, videos, len(videos), len(views), len(dated), _commented(db, scan.id)),
    }


def _limits(
    scan: CompetitorScan,
    videos: list[CompetitorVideo],
    count: int,
    with_views: int,
    dated: int,
    commented: set[int],
) -> list[str]:
    notes = []
    if scan.status != "done":
        notes.append(f"Lượt quét đang ở trạng thái {scan.status}: số liệu có thể chưa đủ.")
    if count and with_views < count:
        notes.append(f"{count - with_views} video không đọc được số view trên lưới.")
    top = captions_top(scan)
    if count and top:
        read = sum(1 for video in videos[:top] if video.caption)
        notes.append(f"Caption đọc được cho {read}/{min(top, count)} video nhiều view nhất; video khác chưa có.")
    sampled = comments_top(scan)
    if count and sampled:
        with_comments = sum(1 for video in videos[:sampled] if video.id in commented)
        notes.append(
            f"Bình luận mẫu có cho {with_comments}/{min(sampled, count)} video nhiều view nhất "
            "(tối đa 30 bình luận đầu mỗi video, không phải toàn bộ)."
        )
    if count and dated == 0:
        notes.append("Lưới Reels không có ngày đăng: chưa tính được tần suất đăng.")
    if count >= (scan.scope or {}).get("max_videos", MAX_VIDEOS_DEFAULT):
        notes.append("Đã chạm giới hạn số video của lượt quét; trang có thể còn video cũ hơn.")
    notes.append("Chỉ quét tab Reels; video thường (tab Video) chưa được quét.")
    return notes


def _commented(db: DbSession, scan_id: int) -> set[int]:
    return set(
        db.scalars(
            select(CompetitorComment.video_id)
            .join(CompetitorVideo, CompetitorVideo.id == CompetitorComment.video_id)
            .where(CompetitorVideo.scan_id == scan_id)
            .distinct()
        )
    )


def comment_samples(db: DbSession, video: CompetitorVideo) -> list[dict]:
    rows = db.scalars(
        select(CompetitorComment).where(CompetitorComment.video_id == video.id).order_by(CompetitorComment.position)
    )
    return [{"text": row.text, "like_count": row.like_count} for row in rows]


def save_report(
    db: DbSession,
    scan: CompetitorScan,
    topics: list,
    pain_points: list,
    recommendations: list,
    markdown: str,
    written_by: str = "",
) -> CompetitorReport:
    """A new report for the scan (earlier ones are kept, the newest is the one read); its numbers are the scan's own,
    summed here, whatever the assistant wrote."""
    text = (markdown or "").strip()
    if not text:
        raise ApiError(422, "empty_report", "Báo cáo trống: cần nội dung markdown")
    if len(text) > REPORT_MARKDOWN_LIMIT:
        raise ApiError(422, "report_too_long", "Báo cáo quá dài (tối đa 60.000 ký tự)")
    report = CompetitorReport(
        scan_id=scan.id,
        written_by=(written_by or "")[:40],
        summary=stats(db, scan),
        topics=list(topics)[:REPORT_LIST_LIMIT],
        pain_points=list(pain_points)[:REPORT_LIST_LIMIT],
        recommendations=list(recommendations)[:REPORT_LIST_LIMIT],
        markdown=text,
    )
    db.add(report)
    db.flush()
    return report


def latest_report(db: DbSession, scan_id: int) -> CompetitorReport | None:
    return db.scalar(
        select(CompetitorReport)
        .where(CompetitorReport.scan_id == scan_id)
        .order_by(CompetitorReport.id.desc())
        .limit(1)
    )


def report_payload(report: CompetitorReport) -> dict:
    return {
        "id": report.id,
        "scan_id": report.scan_id,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "written_by": report.written_by,
        "summary": report.summary,
        "topics": report.topics,
        "pain_points": report.pain_points,
        "recommendations": report.recommendations,
        "markdown": report.markdown,
    }


def video_payload(video: CompetitorVideo, rank: int | None = None) -> dict:
    return {
        **({"rank": rank} if rank is not None else {}),
        "fb_video_id": video.fb_video_id,
        "url": video.url,
        "type": video.type,
        "views": video.views,
        "views_raw": video.views_raw,
        "grid_position": video.position,
        "caption": video.caption,
        "duration_s": video.duration_s,
        "posted_at": video.posted_at.isoformat() if video.posted_at else None,
        "audio_name": video.audio_name,
        "reactions": video.reactions,
        "comments": video.comments,
        "shares": video.shares,
    }


def scan_payload(scan: CompetitorScan) -> dict:
    competitor = scan.competitor
    return {
        "id": scan.id,
        "status": scan.status,
        "videos_found": scan.videos_found,
        "max_videos": (scan.scope or {}).get("max_videos", MAX_VIDEOS_DEFAULT),
        "fetch_captions_top_n": captions_top(scan),
        "fetch_comments_top_n": comments_top(scan),
        "created_at": scan.created_at.isoformat() if scan.created_at else None,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "finished_at": scan.finished_at.isoformat() if scan.finished_at else None,
        "error": scan.error,
        "competitor": competitor_payload(competitor),
    }


def competitor_payload(competitor: Competitor) -> dict:
    return {
        "id": competitor.id,
        "fb_url": competitor.fb_url,
        "kind": competitor.kind,
        "name": competitor.name,
        "followers": competitor.followers,
        "reels_url": parse_url(competitor.fb_url)["reels_url"],
    }


def list_competitors(db: DbSession, user_id: int) -> list[dict]:
    """The member's competitors, newest first, each with its latest scan and that scan's view total."""
    competitors = db.scalars(
        select(Competitor).where(Competitor.owner_id == user_id).order_by(Competitor.id.desc())
    ).all()
    rows = []
    for competitor in competitors:
        latest = db.scalar(
            select(CompetitorScan)
            .where(CompetitorScan.competitor_id == competitor.id)
            .order_by(CompetitorScan.id.desc())
            .limit(1)
        )
        total = None
        if latest is not None:
            total = db.scalar(select(func.sum(CompetitorVideo.views)).where(CompetitorVideo.scan_id == latest.id))
        rows.append(
            {
                **competitor_payload(competitor),
                "latest_scan": scan_payload(latest) | {"total_views": int(total or 0)} if latest else None,
            }
        )
    return rows
