"""A post's link pasted on "Bài đăng" ("Dán link bài đã đăng"): which platform and post it is, the link written one
way, what the platform says of it (oEmbed: title, channel, thumbnail; no views), its channel among the team's, and
the video it most likely is (spec §4.2, §4.4; docs/decisions/2026-11-14-posts-board.md).

oEmbed needs no key and is read in the request, with a short timeout: a member waits for the preview of what they
pasted, and it is not long work like a script or a render."""

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DbSession

from . import config, youtube
from .models import AffiliateAccount, Channel, Fanpage, Publication, TikTokConnection, Video
from .videos import split_scenes, thumbnail_url, video_name

TIMEOUT = 8.0
MAX_REDIRECTS = 3
MAX_LINKS = 50
MAX_URL_LENGTH = 500

TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}
TIKTOK_SHORT_HOSTS = {"vt.tiktok.com", "vm.tiktok.com"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
FACEBOOK_HOSTS = {"facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com"}
FACEBOOK_SHORT_HOSTS = {"fb.watch"}
# Where a short link may lead: anything else is refused, so a pasted link never makes the api call another host.
REDIRECT_HOSTS = TIKTOK_HOSTS | TIKTOK_SHORT_HOSTS | FACEBOOK_HOSTS | FACEBOOK_SHORT_HOSTS

TIKTOK_PATH = re.compile(r"^/@([A-Za-z0-9._]{2,24})/video/(\d{6,25})/?$")
TIKTOK_HANDLE = re.compile(r"^/@([A-Za-z0-9._]{2,24})/?$")
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_HANDLE = re.compile(r"^/(@[A-Za-z0-9._-]{3,30})/?")
YOUTUBE_CHANNEL = re.compile(r"^/channel/(UC[A-Za-z0-9_-]{22})/?")
FACEBOOK_REEL = re.compile(r"^/reel/(\d{5,25})/?$")
FACEBOOK_VIDEO = re.compile(r"^/([A-Za-z0-9.\-]{1,80})/videos/(?:[^/]+/)?(\d{5,25})/?$")
FACEBOOK_ID = re.compile(r"^\d{5,25}$")

PLATFORM_LABELS = {"facebook": "Facebook", "tiktok": "TikTok", "youtube": "YouTube"}


class LinkError(Exception):
    """Why a pasted link is not taken: `code` for the web, `message` in Vietnamese."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def invalid_link() -> LinkError:
    return LinkError("invalid", "Link không hợp lệ")


def unreachable() -> LinkError:
    return LinkError("unreachable", "Không truy cập được")


@dataclass
class Link:
    platform: str
    external_id: str
    url: str
    handle: str | None = None  # a TikTok link names its account


def _parts(raw: str):
    value = raw.strip()
    if not value or len(value) > MAX_URL_LENGTH:
        raise invalid_link()
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    try:
        parts = urlsplit(value)
    except ValueError:
        raise invalid_link() from None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise invalid_link()
    return parts


def is_short(raw: str) -> bool:
    parts = _parts(raw)
    host = parts.hostname.lower()
    return (
        host in TIKTOK_SHORT_HOSTS
        or host in FACEBOOK_SHORT_HOSTS
        or (host in TIKTOK_HOSTS and parts.path.startswith("/t/"))
        or (host in FACEBOOK_HOSTS and parts.path.startswith("/share/"))
    )


def parse(raw: str) -> Link:
    """The post a full link points at, its tracking query dropped; LinkError("invalid") for anything else."""
    parts = _parts(raw)
    host, path = parts.hostname.lower(), parts.path
    if host in TIKTOK_HOSTS:
        match = TIKTOK_PATH.match(path)
        if match:
            handle, video_id = match.groups()
            return Link("tiktok", video_id, f"https://www.tiktok.com/@{handle}/video/{video_id}", handle.lower())
    elif host == "youtu.be" or host in YOUTUBE_HOSTS:
        if host == "youtu.be":
            candidate = path.strip("/")
        elif path.startswith("/shorts/"):
            candidate = path.removeprefix("/shorts/").strip("/")
        elif path == "/watch":
            candidate = (parse_qs(parts.query).get("v") or [""])[0]
        else:
            candidate = ""
        if YOUTUBE_ID.match(candidate):
            return Link("youtube", candidate, f"https://www.youtube.com/shorts/{candidate}")
    elif host in FACEBOOK_HOSTS:
        if match := FACEBOOK_REEL.match(path):
            return Link("facebook", match.group(1), f"https://www.facebook.com/reel/{match.group(1)}")
        if match := FACEBOOK_VIDEO.match(path):
            page, video_id = match.groups()
            return Link("facebook", video_id, f"https://www.facebook.com/{page}/videos/{video_id}")
        if path.rstrip("/") == "/watch":
            candidate = (parse_qs(parts.query).get("v") or [""])[0]
            if FACEBOOK_ID.match(candidate):
                return Link("facebook", candidate, f"https://www.facebook.com/watch/?v={candidate}")
    raise invalid_link()


def resolve(raw: str, client: httpx.Client) -> Link:
    """A short link (vt.tiktok.com, fb.watch, …) followed, at most three hops and only within the platforms' hosts."""
    url = _parts(raw).geturl()
    for _ in range(MAX_REDIRECTS + 1):
        if not is_short(url):
            return parse(url)
        try:
            response = client.get(url, follow_redirects=False)
        except httpx.HTTPError:
            raise unreachable() from None
        location = response.headers.get("location")
        if response.status_code not in (301, 302, 303, 307, 308) or not location:
            raise unreachable()
        url = str(httpx.URL(url).join(location))
        if (urlsplit(url).hostname or "").lower() not in REDIRECT_HOSTS:
            raise invalid_link()
    raise unreachable()


def read(raw: str, client: httpx.Client) -> Link:
    return resolve(raw, client) if is_short(raw) else parse(raw)


@dataclass
class Meta:
    """What oEmbed says of a post. `handle` is the channel's, lower case with its "@" for YouTube."""

    title: str = ""
    handle: str | None = None
    channel_id: str | None = None
    author_name: str = ""
    thumbnail_url: str | None = None
    # From the YouTube Data API, with the team's key: when it went live and its length.
    published_at: datetime | None = None
    duration: float | None = None


def oembed(link: Link, client: httpx.Client) -> Meta | None:
    """The platform's oEmbed answer: None when the platform has none to ask (Facebook needs a token); LinkError
    ("unreachable") when the post is gone or private (any 4xx). A network error or 5xx is also "unreachable": the
    member may paste it again."""
    if link.platform == "facebook":
        return None
    endpoint = config.tiktok_oembed_url() if link.platform == "tiktok" else config.youtube_oembed_url()
    try:
        response = client.get(endpoint, params={"url": link.url, "format": "json"})
    except httpx.HTTPError:
        raise unreachable() from None
    if response.status_code != 200:
        raise unreachable()
    try:
        data = response.json()
    except ValueError:
        raise unreachable() from None
    meta = Meta(
        title=str(data.get("title") or ""),
        author_name=str(data.get("author_name") or ""),
        thumbnail_url=data.get("thumbnail_url") or None,
    )
    if link.platform == "tiktok":
        meta.handle = str(data.get("author_unique_id") or link.handle or "").lower() or None
    else:
        author = urlsplit(str(data.get("author_url") or ""))
        if match := YOUTUBE_HANDLE.match(author.path):
            meta.handle = match.group(1).lower()
        elif match := YOUTUBE_CHANNEL.match(author.path):
            meta.channel_id = match.group(1)
        if youtube.enabled():
            try:
                item = youtube.videos([link.external_id]).get(link.external_id)
            except youtube.YouTubeError:
                item = None  # oEmbed answered: the post is there, only its time and length stay unknown
            if item is not None:
                meta.published_at, meta.duration = youtube.published_at(item), youtube.duration_seconds(item)
                meta.channel_id = (item.get("snippet") or {}).get("channelId") or meta.channel_id
    return meta


# --- Channels ---


@dataclass
class ChannelRef:
    """A channel a post is on: `kind` is "fanpage", "tiktok" (an affiliate account) or "youtube" (a `channels` row)."""

    kind: str
    id: int
    name: str

    def payload(self) -> dict:
        return {"kind": self.kind, "id": self.id, "name": self.name}


def tiktok_handle(account: AffiliateAccount, connection: TikTokConnection | None) -> str | None:
    if connection is not None and connection.username:
        return connection.username.lower().lstrip("@")
    if account.profile_url:
        try:
            parts = urlsplit(account.profile_url.strip())
        except ValueError:
            return None
        if match := TIKTOK_HANDLE.match(parts.path):
            return match.group(1).lower()
    return None


def tiktok_accounts(db: DbSession) -> list[tuple[AffiliateAccount, str | None]]:
    """The team's TikTok accounts in use, with the handle each is known by."""
    connections = {row.affiliate_account_id: row for row in db.scalars(select(TikTokConnection))}
    accounts = db.scalars(
        select(AffiliateAccount)
        .where(AffiliateAccount.platform == "tiktok", AffiliateAccount.active.is_(True))
        .order_by(AffiliateAccount.id)
    )
    return [(account, tiktok_handle(account, connections.get(account.id))) for account in accounts]


def find_channel(db: DbSession, link: Link, meta: Meta | None) -> ChannelRef | None:
    if link.platform == "tiktok":
        handle = (meta.handle if meta and meta.handle else link.handle) or ""
        for account, known in tiktok_accounts(db):
            if known and known == handle.lower():
                return ChannelRef("tiktok", account.id, account.name)
        return None
    if link.platform == "youtube" and meta is not None:
        for channel in db.scalars(select(Channel).where(Channel.platform == "youtube")):
            if (meta.handle and channel.handle.lower() == meta.handle) or (
                meta.channel_id and channel.external_id == meta.channel_id
            ):
                return ChannelRef("youtube", channel.id, channel.name)
    return None


def my_pages(db: DbSession, user_id: int) -> list[Fanpage]:
    """The Pages a member records a Facebook post on: their own, as only a Page's owner posts to it (2026-11-09)."""
    return list(
        db.scalars(select(Fanpage).where(Fanpage.owner_id == user_id, Fanpage.active.is_(True)).order_by(Fanpage.name))
    )


def existing_post(db: DbSession, link: Link) -> Publication | None:
    """The post already recorded for this link. A reel the app posted is known by `remote_id`, which the publish job
    and "Sửa link reel" set, so it is looked up there too."""
    same = Publication.external_id == link.external_id
    if link.platform == "facebook":
        same = or_(same, Publication.remote_id == link.external_id)
    return db.scalar(
        select(Publication)
        .where(Publication.platform == link.platform, same, Publication.status != "cancelled")
        .order_by(Publication.id)
        .limit(1)
    )


# --- Matching a post to a video (§4.4) ---

AUTO_SCORE = 0.85
AUTO_LEAD = 0.10
SUGGEST_SCORE = 0.50
WINDOW = timedelta(days=60)

_HASHTAG = re.compile(r"#\S+")
_DOTTED = re.compile(r"(?<=\w)\.(?=\w)")
_NOT_WORD = re.compile(r"[^0-9a-z]+")


def normalize(text: str) -> str:
    """Lower case, no Vietnamese marks, no hashtags, emoji or punctuation; "th.uốc" is "thuoc"."""
    text = _HASHTAG.sub(" ", text or "")
    text = _DOTTED.sub("", text)
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    return " ".join(_NOT_WORD.sub(" ", text).split())


def similarity(left: str, right: str) -> float:
    """Token-set ratio (0–1): the words both share, then each side's own, compared as sorted strings."""
    a, b = set(normalize(left).split()), set(normalize(right).split())
    if not a or not b:
        return 0.0
    shared = " ".join(sorted(a & b))
    first = f"{shared} {' '.join(sorted(a - b))}".strip()
    second = f"{shared} {' '.join(sorted(b - a))}".strip()

    def ratio(x: str, y: str) -> float:
        return difflib.SequenceMatcher(None, x, y).ratio() if x and y else 0.0

    return max(ratio(shared, first), ratio(shared, second), ratio(first, second))


def score(text: str, published_at: datetime, video: Video, names: list[str], duration: float | None = None) -> float:
    """§4.4: the text 0.6, the length 0.3 (left out, and the rest weighed up, when the post's is unknown), the time
    from render to post 0.1."""
    words = max((similarity(text, name) for name in names if name), default=0.0)
    days = (published_at - video.rendered_at).total_seconds() / 86400 if video.rendered_at else 999
    timing = 1.0 if days <= 14 else 0.5 if days <= 60 else 0.0
    if duration is None or not video.mp4_seconds:
        return (0.6 * words + 0.1 * timing) / 0.7
    gap = abs(duration - video.mp4_seconds)
    length = 1.0 if gap <= 1 else 0.5 if gap <= 3 else 0.0
    return 0.6 * words + 0.3 * length + 0.1 * timing


@dataclass
class Match:
    video: Video | None = None
    score: float | None = None
    confirmed: bool = False
    suggestions: list[tuple[Video, float]] = field(default_factory=list)


def candidates(db: DbSession, published_at: datetime) -> list[Video]:
    return list(
        db.scalars(
            select(Video).where(
                Video.rendered_at.is_not(None),
                Video.rendered_at <= published_at,
                Video.rendered_at >= published_at - WINDOW,
            )
        )
    )


def match_video(db: DbSession, text: str, published_at: datetime, duration: float | None = None) -> Match:
    """The video a post most likely is: chosen by itself at 85% and 10 points ahead of the next, else suggested."""
    if not normalize(text):
        return Match()
    ranked = []
    for video in candidates(db, published_at):
        title, _ = split_scenes(db, video)
        names = [video_name(video, title), video.caption, video.topic]
        ranked.append((video, score(text, published_at, video, names, duration)))
    ranked.sort(key=lambda row: row[1], reverse=True)
    if not ranked:
        return Match()
    best, best_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    confirmed = best_score >= AUTO_SCORE and best_score - runner_up >= AUTO_LEAD
    suggestions = [row for row in ranked[:5] if row[1] >= SUGGEST_SCORE]
    return Match(
        video=best if confirmed else None,
        score=best_score,
        confirmed=confirmed,
        suggestions=suggestions,
    )


def video_ref(db: DbSession, video: Video, value: float | None = None) -> dict:
    title, _ = split_scenes(db, video)
    return {
        "id": video.id,
        "name": video_name(video, title),
        "thumbnail_url": thumbnail_url(video),
        **({"score": round(value * 100)} if value is not None else {}),
    }
