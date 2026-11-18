"""'Phân tích đối thủ': a member pastes a competitor's Facebook link, their own Chrome reads its Reels grid through the
team's extension (never the server: Facebook shows views only to a signed-in browser), and the numbers are summed
here in code, so the member's Claude analyses topics and pains through MCP without adding anything up itself.

docs/decisions/2026-11-17-competitor-analyzer.md; the extension's side is extension/facebook-reels.js.
"""

import base64
import binascii
import csv
import io
import re
import secrets
import statistics
import unicodedata
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from PIL import Image
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from . import uploads
from .errors import ApiError
from .models import (
    COMPETITOR_VIDEO_TYPES,
    AppSetting,
    Competitor,
    CompetitorComment,
    CompetitorReport,
    CompetitorScan,
    CompetitorVideo,
    User,
)
from .sessions import now
from .storage import get_storage

MAX_VIDEOS_DEFAULT = 500
MAX_VIDEOS_LIMIT = 2000
# M3: the most viewed videos whose own page is opened for caption, sound and reactions (4–8 s apart).
# M5: besides the top reels, a video every TIMELINE_STEP places down each grid (the newest and the oldest
# always) has its own page opened for its posting date, so how often the competitor posts is read from the grid.
TIMELINE_STEP = 50
TIMELINE_LIMIT = 30
VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")
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
    return {
        "fb_url": url,
        "fb_id": None,
        "kind": "page",
        "reels_url": url + "/reels/",
        "videos_url": url + "/videos/",
    }


def _numeric(fb_id: str) -> dict:
    url = f"https://www.facebook.com/profile.php?id={fb_id}"
    return {
        "fb_url": url,
        "fb_id": fb_id,
        "kind": "profile",
        "reels_url": url + "&sk=reels_tab",
        "videos_url": url + "&sk=videos",
    }


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


# Facebook's posting time as written on a video's page: relative ("5 phút", "3 giờ", "2 ngày", "1 tuần", "3d"),
# "Hôm qua lúc 08:00", or a date ("17 tháng 10", "17 tháng 10, 2024", "17/10/2024", "October 17, 2024").
RELATIVE = re.compile(
    r"^(\d+)\s*(giây|phút|giờ|ngày|tuần|tháng|năm|s|m|h|d|w|y|secs?|mins?|hrs?|hours?|days?|weeks?|months?|years?)$"
)
UNIT_DAYS = {
    "giây": 1 / 86400,
    "s": 1 / 86400,
    "sec": 1 / 86400,
    "secs": 1 / 86400,
    "phút": 1 / 1440,
    "m": 1 / 1440,
    "min": 1 / 1440,
    "mins": 1 / 1440,
    "giờ": 1 / 24,
    "h": 1 / 24,
    "hr": 1 / 24,
    "hrs": 1 / 24,
    "hour": 1 / 24,
    "hours": 1 / 24,
    "ngày": 1,
    "d": 1,
    "day": 1,
    "days": 1,
    "tuần": 7,
    "w": 7,
    "week": 7,
    "weeks": 7,
    "tháng": 30,
    "month": 30,
    "months": 30,
    "năm": 365,
    "y": 365,
    "year": 365,
    "years": 365,
}
MONTHS_EN = {
    name: number
    for number, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ],
        start=1,
    )
    for name in names
}
CLOCK = re.compile(r"(?:lúc|at)\s+(\d{1,2}):(\d{2})\s*(am|pm|sa|ch)?")


def parse_posted(raw: str | None, at: datetime) -> datetime | None:
    """When a video was posted, from the time its page shows, `at` being when it was read. Relative times are as
    exact as Facebook wrote them; a date without a year is the last such day not after `at` (Vietnam time)."""
    if not raw:
        return None
    text = unicodedata.normalize("NFC", raw).lower().replace("\u00a0", " ").strip()
    text = re.sub(r"\s+(trước|ago)$", "", text).strip(" ·.")
    if text in ("vừa xong", "just now"):
        return at
    found = RELATIVE.match(text)
    if found:
        return at - timedelta(days=int(found[1]) * UNIT_DAYS[found[2]])
    local = at.astimezone(VIETNAM)
    clock = CLOCK.search(text)
    hour, minute = 0, 0
    if clock:
        hour, minute = int(clock[1]) % 24, int(clock[2])
        if clock[3] in ("pm", "ch") and hour < 12:
            hour += 12
        if clock[3] in ("am", "sa") and hour == 12:
            hour = 0
        text = text[: clock.start()].strip(" ,")
    if text in ("hôm qua", "yesterday"):
        day = (local - timedelta(days=1)).date()
        return datetime(day.year, day.month, day.day, hour, minute, tzinfo=VIETNAM).astimezone(UTC)
    day = month = year = None
    if (found := re.fullmatch(r"(\d{1,2})\s+tháng\s+(\d{1,2})(?:,?\s+(?:năm\s+)?(\d{4}))?", text)) or (
        found := re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", text)
    ):
        day, month, year = int(found[1]), int(found[2]), found[3]
    elif found := re.fullmatch(r"([a-z]+)\s+(\d{1,2})(?:,?\s+(\d{4}))?", text):
        month, day, year = MONTHS_EN.get(found[1]), int(found[2]), found[3]
    elif found := re.fullmatch(r"(\d{1,2})\s+([a-z]+)(?:,?\s+(\d{4}))?", text):
        day, month, year = int(found[1]), MONTHS_EN.get(found[2]), found[3]
    if not day or not month:
        return None
    try:
        posted = datetime(int(year) if year else local.year, month, day, hour, minute, tzinfo=VIETNAM)
    except ValueError:
        return None
    if not year and posted > local:
        try:
            posted = posted.replace(year=posted.year - 1)
        except ValueError:
            return None
    return posted.astimezone(UTC)


def compare(db: DbSession, competitor_ids: list[int]) -> list[dict]:
    """Any of the team's competitors side by side (M5): for each, its latest scan that read anything (done or partial) and that scan's
    numbers, summed in code. A competitor with no such scan is listed with `scan: null`."""
    rows = []
    for competitor_id in competitor_ids:
        competitor = team_competitor(db, competitor_id)
        scan = db.scalar(
            select(CompetitorScan)
            .where(
                CompetitorScan.competitor_id == competitor.id,
                CompetitorScan.meta_only.is_(False),
                CompetitorScan.status.in_(("done", "partial")),
            )
            .order_by(CompetitorScan.id.desc())
            .limit(1)
        )
        summary = None
        if scan is not None:
            numbers = stats(db, scan)
            summary = {
                key: numbers[key]
                for key in (
                    "scan_id",
                    "status",
                    "videos",
                    "by_type",
                    "total_views",
                    "median_views",
                    "max_views",
                    "buckets",
                    "top10_share",
                    "videos_per_week",
                    "newest_posted_at",
                    "oldest_posted_at",
                )
            }
            summary["finished_at"] = scan.finished_at.isoformat() if scan.finished_at else None
        rows.append({"competitor": competitor_payload(competitor), "scan": summary})
    return rows


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
    include_videos: bool = False,
    meta_only: bool = False,
) -> CompetitorScan:
    """A queued scan of the competitor at `url` (made on first use). One waiting or running scan per competitor and
    kind (videos, or the header only): a second request answers the one already there."""
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
            CompetitorScan.competitor_id == competitor.id,
            CompetitorScan.meta_only.is_(meta_only),
            CompetitorScan.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        return active
    scan = CompetitorScan(
        competitor_id=competitor.id,
        owner_id=user_id,
        status="queued",
        meta_only=meta_only,
        scope={
            "meta_only": True,
        }
        if meta_only
        else {
            "reels": True,
            "videos": bool(include_videos),
            "max_videos": max(1, min(max_videos, MAX_VIDEOS_LIMIT)),
            "fetch_captions_top_n": max(0, min(captions_top, CAPTIONS_TOP_LIMIT)),
            "fetch_comments_top_n": max(0, min(comments_top, COMMENTS_TOP_LIMIT, captions_top)),
        },
    )
    db.add(scan)
    db.flush()
    return scan


# The whole team reads every competitor, scan and report (decision 2026-11-17-competitor-team-read); only the member
# who scans a competitor scans it again, resumes, deletes it or sends its scan's data (the extension's batches).
NOT_OWNER = "Chỉ người quét đối thủ này mới làm được việc này"


def team_scan(db: DbSession, scan_id: int, lock: bool = False) -> CompetitorScan:
    """Any member's scan, to read (or to save a report on)."""
    query = select(CompetitorScan).where(CompetitorScan.id == scan_id)
    scan = db.scalar(query.with_for_update() if lock else query)
    if scan is None:
        raise ApiError(404, "scan_not_found", "Không tìm thấy lượt quét này")
    return scan


def team_competitor(db: DbSession, competitor_id: int) -> Competitor:
    competitor = db.get(Competitor, competitor_id)
    if competitor is None:
        raise ApiError(404, "competitor_not_found", "Không tìm thấy đối thủ này")
    return competitor


def own_scan(db: DbSession, scan_id: int, user_id: int, lock: bool = False) -> CompetitorScan:
    """A scan its member changes: a teammate's answers 403."""
    scan = team_scan(db, scan_id, lock)
    if scan.owner_id != user_id:
        raise ApiError(403, "not_scan_owner", NOT_OWNER)
    return scan


def own_competitor(db: DbSession, competitor_id: int, user_id: int) -> Competitor:
    competitor = team_competitor(db, competitor_id)
    if competitor.owner_id != user_id:
        raise ApiError(403, "not_scan_owner", NOT_OWNER)
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


def enrich_targets(db: DbSession, scan: CompetitorScan) -> list[dict]:
    """The videos of a running scan whose own page the extension opens next, each {fb_video_id, url, comments}: the
    most viewed (M3; the first comments_top(scan) of them also have their comments sampled, M4), then the grid's
    timeline samples (M5), only for their posting date."""
    ensure_running(scan)
    scan.heartbeat_at = now()
    top = list(
        db.scalars(
            select(CompetitorVideo)
            .where(CompetitorVideo.scan_id == scan.id, CompetitorVideo.views.is_not(None))
            .order_by(CompetitorVideo.views.desc(), CompetitorVideo.id)
            .limit(captions_top(scan))
        )
    )
    sampled = comments_top(scan)
    targets = [
        {"fb_video_id": video.fb_video_id, "url": video.url, "comments": rank < sampled}
        for rank, video in enumerate(top)
    ]
    chosen = {video.id for video in top}
    for video in timeline_samples(db, scan.id):
        if video.id not in chosen:
            targets.append({"fb_video_id": video.fb_video_id, "url": video.url, "comments": False})
            chosen.add(video.id)
    return targets


def timeline_samples(db: DbSession, scan_id: int) -> list[CompetitorVideo]:
    """For each grid (Reels, Videos), the newest and the oldest video and one every TIMELINE_STEP places between."""
    picked = []
    for kind in COMPETITOR_VIDEO_TYPES:
        grid = list(
            db.scalars(
                select(CompetitorVideo)
                .where(
                    CompetitorVideo.scan_id == scan_id,
                    CompetitorVideo.type == kind,
                    CompetitorVideo.position.is_not(None),
                )
                .order_by(CompetitorVideo.position)
            )
        )
        if not grid:
            continue
        places = sorted({*range(0, len(grid), TIMELINE_STEP), len(grid) - 1})[:TIMELINE_LIMIT]
        picked.extend(grid[place] for place in places)
    return picked


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
        posted_raw = (detail.get("posted_raw") or "").strip()[:80]
        posted = parse_posted(posted_raw, now())
        if posted is not None:
            video.posted_raw, video.posted_at = posted_raw, posted
        for field in ("reactions", "comments", "shares"):
            value = parse_views(detail.get(f"{field}_raw"))
            if value is not None:
                setattr(video, field, value)
        if detail.get("thumbnail"):
            save_thumbnail(scan.competitor_id, video, detail["thumbnail"])
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
    db: DbSession,
    scan: CompetitorScan,
    status: str,
    error: str | None,
    name: str | None,
    followers: str | None,
    is_verified: bool | None = None,
    avatar: str | None = None,
) -> None:
    """The page's last word: done, partial (stopped early: a checkpoint, the window closed, the time limit) or failed.
    What the scan read from the Page's header (name, followers, verified badge, avatar) is kept even then."""
    ensure_running(scan)
    scan.status = status
    scan.error = (error or "").strip()[:500] or None
    scan.finished_at = now()
    scan.heartbeat_at = now()
    competitor = scan.competitor
    read = False
    if name and name.strip():
        competitor.name = name.strip()[:200]
        read = True
    if followers:
        competitor.followers = parse_views(followers)
        read = read or competitor.followers is not None
    if is_verified is not None:
        competitor.is_verified = is_verified
        read = True
    if avatar and save_avatar(competitor, avatar):
        read = True
    if read:
        competitor.meta_updated_at = now()
    if status == "done" and not scan.meta_only:
        apply_threshold(db, scan)


SETTING_KEY = "competitor_threshold"
MIN_HITS_RANGE = (1, 100)
MIN_VIEWS_RANGE = (1_000, 100_000_000)


def threshold_settings(db: DbSession) -> dict:
    """The team's rule for "Tự động" (Cài đặt › Phân tích đối thủ): a channel with `min_hits` videos of `min_views`
    or more is big and keeps only those. Defaults are the spec's 10 videos of 100K."""
    row = db.get(AppSetting, SETTING_KEY)
    saved = row.value if row is not None and isinstance(row.value, dict) else {}
    hits, views = saved.get("min_hits"), saved.get("min_views")
    return {
        "min_hits": hits
        if isinstance(hits, int) and MIN_HITS_RANGE[0] <= hits <= MIN_HITS_RANGE[1]
        else BIG_CHANNEL_MIN_HITS,
        "min_views": views
        if isinstance(views, int) and MIN_VIEWS_RANGE[0] <= views <= MIN_VIEWS_RANGE[1]
        else MIN_VIEWS_THRESHOLD,
    }


def save_threshold_settings(db: DbSession, min_hits: int, min_views: int, user_id: int) -> dict:
    value = {"min_hits": min_hits, "min_views": min_views}
    row = db.get(AppSetting, SETTING_KEY)
    if row is None:
        db.add(AppSetting(key=SETTING_KEY, value=value, updated_by_id=user_id))
    else:
        row.value, row.updated_by_id = value, user_id
    return value


def threshold_for(mode: str, views: list[int], rule: dict | None = None) -> int | None:
    """The views a video needs to be kept, None to keep all: "auto" keeps only the videos above the team's threshold
    on a big channel."""
    rule = rule or {"min_hits": BIG_CHANNEL_MIN_HITS, "min_views": MIN_VIEWS_THRESHOLD}
    if mode == "100k":
        return 100_000
    if mode == "1m":
        return 1_000_000
    if mode == "auto" and sum(1 for value in views if value >= rule["min_views"]) >= rule["min_hits"]:
        return rule["min_views"]
    return None


def views_label(views: int) -> str:
    """100000 as "100K", 1000000 as "1M"."""
    return f"{views / 1_000_000:g}M" if views >= 1_000_000 else f"{views / 1_000:g}K"


def apply_threshold(db: DbSession, scan: CompetitorScan) -> None:
    """After a finished scan: a big channel keeps only its videos above the threshold. The numbers over everything
    read are summed first and kept in `stats_snapshot` (stats() answers with them), because the dropped videos are
    deleted. A video whose own page was read (a caption or a posting date) stays: the timeline samples and the
    captions belong to it. A video with no readable views is never dropped."""
    scan.stats_snapshot = None
    videos = videos_of(db, scan.id)
    views = [video.views for video in videos if video.views is not None]
    scan.scanned_count = len(videos)
    threshold = threshold_for(scan.competitor.video_threshold_mode, views, threshold_settings(db))
    scan.threshold_applied = threshold
    if threshold is None:
        scan.stored_count = len(videos)
        return
    snapshot = stats(db, scan)
    scan.stats_snapshot = {key: value for key, value in snapshot.items() if key not in ("scan_id", "status")}
    drop = [
        video.id
        for video in videos
        if video.views is not None
        and video.views < threshold
        and video.posted_at is None
        and not video.caption
        and not video.thumb_key
    ]
    if drop:
        db.execute(delete(CompetitorVideo).where(CompetitorVideo.id.in_(drop)))
    scan.stored_count = len(videos) - len(drop)


THRESHOLD_MODES = ("auto", "all", "100k", "1m")
# A channel with at least BIG_CHANNEL_MIN_HITS videos of MIN_VIEWS_THRESHOLD views is "big": only those are kept.
BIG_CHANNEL_MIN_HITS = 10
MIN_VIEWS_THRESHOLD = 100_000

AVATAR_SIZE = 128
AVATAR_DATA_LIMIT = 150_000


def _jpeg_copy(data_url: str, size: int) -> bytes | None:
    """A `data:image/...;base64,` URL from the extension, decoded by Pillow and re-encoded as a JPEG of at most
    `size` px a side, so whatever was sent is never stored or served as it came. None when it is not an image."""
    head, _, body = data_url.partition(",")
    if not head.startswith("data:image/") or not head.endswith(";base64") or len(data_url) > AVATAR_DATA_LIMIT:
        return None
    try:
        raw = base64.b64decode(body, validate=True)
        uploads.image_extension(raw)  # decodes it fully and refuses a bomb or anything but JPG, PNG, WebP
        with Image.open(io.BytesIO(raw)) as picture:
            picture = picture.convert("RGB")
            picture.thumbnail((size, size))
            out = io.BytesIO()
            picture.save(out, "JPEG", quality=85)
            return out.getvalue()
    except (binascii.Error, ValueError, OSError):
        return None


def save_avatar(competitor: Competitor, data_url: str) -> bool:
    """Keeps a small copy of the Page's avatar (Facebook's own link is signed and expires). False when it is not an
    image; the avatar already kept then stays."""
    jpeg = _jpeg_copy(data_url, AVATAR_SIZE)
    if jpeg is None:
        return False
    storage = get_storage()
    key = f"competitors/{competitor.id}/avatar-{secrets.token_hex(4)}.jpg"
    storage.save_bytes(key, jpeg)
    storage.delete(competitor.avatar_key)
    competitor.avatar_key = key
    return True


def save_thumbnail(competitor_id: int, video: CompetitorVideo, data_url: str) -> bool:
    """A small picture of a video whose page the extension opened. One file per competitor and video, so a later scan
    of the same video replaces it."""
    jpeg = _jpeg_copy(data_url, AVATAR_SIZE)
    if jpeg is None:
        return False
    key = f"competitors/{competitor_id}/thumbs/{video.fb_video_id}.jpg"
    get_storage().save_bytes(key, jpeg)
    video.thumb_key = key
    return True


def resume(scan: CompetitorScan) -> None:
    """ "Tiếp tục": a stopped scan is queued again; its videos stay and are updated as the grid is read again."""
    if scan.status not in ("partial", "failed"):
        raise ApiError(409, "scan_not_resumable", "Chỉ tiếp tục được lượt quét dừng giữa chừng hoặc bị lỗi")
    scan.status = "queued"
    scan.finished_at = None
    scan.error = None
    # Read again from the top: the numbers are summed afresh when it ends.
    scan.stats_snapshot = None


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
    """The scan's numbers, in code so an assistant never adds them up itself. A scan that kept only its videos above
    a threshold answers with the numbers summed over everything it read (apply_threshold)."""
    if scan.stats_snapshot:
        note = (
            f"Chỉ lưu {scan.stored_count} video từ {views_label(scan.threshold_applied or 0)} view trong "
            f"{scan.scanned_count} video đã đọc; số liệu tính trên toàn bộ video đã đọc."
        )
        return {
            **scan.stats_snapshot,
            "scan_id": scan.id,
            "status": scan.status,
            "limits": [note, *scan.stats_snapshot["limits"]],
        }
    videos = videos_of(db, scan.id)
    views = [video.views for video in videos if video.views is not None]
    total = sum(views)
    top10 = sum(views[:10])  # videos_of sorts by views, highest first
    dated = sorted(video.posted_at for video in videos if video.posted_at is not None)
    frequency = {kind: _frequency(videos, kind) for kind in COMPETITOR_VIDEO_TYPES}
    main = frequency["reel"] or frequency["video"]
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
        "by_type": {kind: sum(1 for video in videos if video.type == kind) for kind in COMPETITOR_VIDEO_TYPES},
        "videos_per_week": main["videos_per_week"] if main else None,
        "frequency": frequency,
        "newest_posted_at": dated[-1].isoformat() if dated else None,
        "oldest_posted_at": dated[0].isoformat() if dated else None,
        "dated_videos": len(dated),
        "limits": _limits(scan, videos, len(videos), len(views), len(dated), _commented(db, scan.id)),
    }


def _frequency(videos: list[CompetitorVideo], kind: str) -> dict | None:
    """How often one grid was posted to, from its dated videos and their places on it (newest first): the videos
    between two dated ones were posted between their dates. Whole span, and each stretch between dated samples."""
    points = sorted(
        (video.position, video.posted_at)
        for video in videos
        if video.type == kind and video.position is not None and video.posted_at is not None
    )
    if len(points) < 2:
        return None

    def per_week(newer, older) -> float | None:
        days = (newer[1] - older[1]).total_seconds() / 86400
        if days < 1 or older[0] <= newer[0]:
            return None
        return round((older[0] - newer[0]) / (days / 7), 1)

    stretches = []
    for newer, older in zip(points, points[1:], strict=False):
        stretches.append(
            {
                "from": older[1].isoformat(),
                "to": newer[1].isoformat(),
                "videos": older[0] - newer[0],
                "videos_per_week": per_week(newer, older),
            }
        )
    return {
        "videos_per_week": per_week(points[0], points[-1]),
        "from": points[-1][1].isoformat(),
        "to": points[0][1].isoformat(),
        "videos": points[-1][0] - points[0][0] + 1,
        "stretches": stretches,
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
        notes.append("Chưa đọc được ngày đăng nào: chưa tính được tần suất đăng.")
    elif count:
        notes.append(
            'Ngày đăng đọc từ trang riêng của từng video (ví dụ "3 ngày", "17 tháng 10"): ngày tương đối là ước '
            "lượng; tần suất tính theo vị trí trên lưới giữa các video có ngày."
        )
    if count >= (scan.scope or {}).get("max_videos", MAX_VIDEOS_DEFAULT):
        notes.append("Đã chạm giới hạn số video của lượt quét; trang có thể còn video cũ hơn.")
    if not (scan.scope or {}).get("videos"):
        notes.append("Chỉ quét tab Reels; video thường (tab Video) không được quét ở lượt này.")
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
    created_by_id: int | None = None,
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
        created_by_id=created_by_id,
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
        "created_by": report.created_by.name if report.created_by else None,
        "summary": report.summary,
        "topics": report.topics,
        "pain_points": report.pain_points,
        "recommendations": report.recommendations,
        "markdown": report.markdown,
    }


def video_payload(video: CompetitorVideo, rank: int | None = None, competitor_id: int | None = None) -> dict:
    return {
        "thumb_url": f"/api/competitors/{competitor_id}/thumbs/{video.fb_video_id}"
        if competitor_id and video.thumb_key
        else None,
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
        "posted_raw": video.posted_raw,
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
        "include_videos": bool((scan.scope or {}).get("videos")),
        "meta_only": scan.meta_only,
        "scanned_count": scan.scanned_count,
        "stored_count": scan.stored_count,
        "threshold_applied": scan.threshold_applied,
        "created_at": scan.created_at.isoformat() if scan.created_at else None,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "finished_at": scan.finished_at.isoformat() if scan.finished_at else None,
        "error": scan.error,
        "competitor": competitor_payload(competitor),
    }


def handle_of(competitor: Competitor) -> str | None:
    """The Page's vanity name ("doanphuonglinh.hr"), None for a `profile.php?id=` address."""
    if competitor.kind == "profile" or "profile.php" in competitor.fb_url:
        return None
    return urlsplit(competitor.fb_url).path.strip("/").split("/")[-1] or None


def display_name(competitor: Competitor) -> str:
    """The name shown everywhere: the member's own, else the one the scan read, else the handle, else "Kênh …" and
    the last six digits of the id."""
    if competitor.custom_name:
        return competitor.custom_name
    if competitor.name:
        return competitor.name
    handle = handle_of(competitor)
    if handle:
        return handle
    return f"Kênh …{(competitor.fb_id or str(competitor.id))[-6:]}"


def avatar_url(competitor: Competitor) -> str | None:
    if not competitor.avatar_key:
        return None
    stamp = int(competitor.meta_updated_at.timestamp()) if competitor.meta_updated_at else 0
    return f"/api/competitors/{competitor.id}/avatar?v={stamp}"


def competitor_payload(competitor: Competitor) -> dict:
    return {
        "id": competitor.id,
        "fb_url": competitor.fb_url,
        "kind": competitor.kind,
        "name": competitor.name,
        "custom_name": competitor.custom_name,
        "display_name": display_name(competitor),
        "handle": handle_of(competitor),
        "fb_id": competitor.fb_id,
        "avatar_url": avatar_url(competitor),
        "is_verified": competitor.is_verified,
        "video_threshold_mode": competitor.video_threshold_mode,
        "has_meta": competitor.meta_updated_at is not None,
        "meta_updated_at": competitor.meta_updated_at.isoformat() if competitor.meta_updated_at else None,
        "followers": competitor.followers,
        "reels_url": parse_url(competitor.fb_url)["reels_url"],
        "videos_url": parse_url(competitor.fb_url)["videos_url"],
        "owner": {"id": competitor.owner_id, "name": competitor.owner.name},
    }


def rename(competitor: Competitor, custom_name: str | None) -> None:
    """The member's own name for the channel; empty or None restores the one the scan read."""
    competitor.custom_name = (custom_name or "").strip()[:200] or None


def set_threshold_mode(competitor: Competitor, mode: str) -> None:
    """Applies from the next scan that ends; videos already dropped are not read again."""
    if mode not in THRESHOLD_MODES:
        raise ApiError(422, "bad_threshold_mode", "Ngưỡng video không hợp lệ")
    competitor.video_threshold_mode = mode


def list_competitors(db: DbSession, user_id: int) -> list[dict]:
    """The team's competitors, the member's own first then newest first, each with its latest scan of videos (not a
    header-only one), that scan's numbers (summed here, not by the page), and whether a header refresh is waiting;
    `is_mine` says whether the member may scan it again, resume, rename or delete it."""
    competitors = db.scalars(
        select(Competitor).order_by((Competitor.owner_id == user_id).desc(), Competitor.id.desc())
    ).all()
    rows = []
    for competitor in competitors:
        scans = select(CompetitorScan).where(CompetitorScan.competitor_id == competitor.id)
        latest = db.scalar(scans.where(CompetitorScan.meta_only.is_(False)).order_by(CompetitorScan.id.desc()).limit(1))
        meta_busy = db.scalar(
            scans.where(CompetitorScan.meta_only.is_(True), CompetitorScan.status.in_(("queued", "running"))).limit(1)
        )
        summary = None
        if latest is not None:
            numbers = stats(db, latest)
            stored = db.scalar(select(func.count()).where(CompetitorVideo.scan_id == latest.id)) or 0
            summary = {
                "total_views": numbers["total_views"],
                "median_views": numbers["median_views"],
                # Videos read; `stored_count` is how many of them are kept and listed.
                "video_count": numbers["videos"],
                "stored_count": stored,
                "reels_count": numbers["by_type"]["reel"],
                "videos_count": numbers["by_type"]["video"],
            }
        rows.append(
            {
                **competitor_payload(competitor),
                "is_mine": competitor.owner_id == user_id,
                "meta_busy": meta_busy is not None,
                "latest_scan": scan_payload(latest) | summary if latest else None,
            }
        )
    return rows


def videos_page(
    db: DbSession,
    competitor: Competitor,
    page: int,
    limit: int,
    sort: str,
    query: str | None = None,
    min_views: int = 0,
) -> dict:
    """The videos of the competitor's latest scan that read any, a page at a time (the page asks 20 at first), most
    viewed first or newest posted first; `has_engagement` and `has_published_at` say whether those columns hold
    anything, so the page hides them when they are empty."""
    scan = db.scalar(
        select(CompetitorScan)
        .where(
            CompetitorScan.competitor_id == competitor.id,
            CompetitorScan.meta_only.is_(False),
            CompetitorScan.videos_found > 0,
        )
        .order_by(CompetitorScan.id.desc())
        .limit(1)
    )
    if scan is None:
        return {
            "scan_id": None,
            "total": 0,
            "page": page,
            "limit": limit,
            "videos": [],
            "has_engagement": False,
            "has_published_at": False,
        }
    everything = videos_of(db, scan.id)  # most viewed first: a video's place here is its rank
    rank_of = {video.id: rank for rank, video in enumerate(everything, start=1)}
    videos = everything
    if min_views:
        videos = [video for video in videos if (video.views or 0) >= min_views]
    words = (query or "").strip().lower()
    if words:
        videos = [video for video in videos if words in (video.caption or "").lower()]
    if sort == "posted":
        dated = sorted((video for video in videos if video.posted_at), key=lambda video: video.posted_at, reverse=True)
        videos = dated + [video for video in videos if not video.posted_at]
    start = (page - 1) * limit
    return {
        "scan_id": scan.id,
        "scanned_count": scan.scanned_count if scan.scanned_count is not None else len(everything),
        "threshold_applied": scan.threshold_applied,
        "total": len(videos),
        "page": page,
        "limit": limit,
        "videos": [video_payload(video, rank_of[video.id], competitor.id) for video in videos[start : start + limit]],
        "has_engagement": any(
            value is not None for video in everything for value in (video.reactions, video.comments, video.shares)
        ),
        "has_published_at": any(video.posted_at is not None for video in everything),
    }


def _safe_cell(value: object) -> str:
    """A cell for a spreadsheet: a caption a competitor wrote may start with `=` or `@`, which Excel would run."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def videos_csv(db: DbSession, competitor: Competitor) -> str:
    """Every video of the latest scan as CSV (with a BOM so Excel reads the Vietnamese), most viewed first."""
    data = videos_page(db, competitor, 1, 100_000, "views")
    out = io.StringIO()
    out.write("\ufeff")
    writer = csv.writer(out)
    writer.writerow(["Hạng", "Loại", "Link", "View", "Caption", "Cảm xúc", "Bình luận", "Chia sẻ", "Ngày đăng"])
    for video in data["videos"]:
        writer.writerow(
            [
                video["rank"],
                "Reels" if video["type"] == "reel" else "Video",
                video["url"],
                video["views"],
                _safe_cell(video["caption"]),
                video["reactions"],
                video["comments"],
                video["shares"],
                video["posted_at"] or "",
            ]
        )
    return out.getvalue()
