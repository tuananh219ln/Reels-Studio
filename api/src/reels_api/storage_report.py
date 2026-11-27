"""`python -m reels_api storage-report`: what the video folders of the storage volume hold, by kind of file and by how
long ago the video was last posted. Read only: it deletes and writes nothing
(docs/specs/video-media-retention/brief.md, step 1)."""

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from .models import Publication, Video

# The file name's start says what a file is (videos.new_key); the order matters, "motion-photo" before "motion".
KINDS = (
    ("video-", "MP4 cuối"),
    ("thumb-", "Ảnh thu nhỏ"),
    ("clip-", "Clip cảnh"),
    ("motion-photo-", "Cảnh động"),
    ("motion-", "Cảnh động"),
    ("scene-", "Ảnh cảnh"),
    ("title-slot-", "Ảnh cảnh"),
    ("card-", "Ảnh cảnh"),
    ("layer-", "Ảnh lớp"),
    ("voice-", "Lời đọc"),
    ("music-", "Nhạc riêng"),
    ("upload-", "MP4 tải lên"),
)
OTHER = "Khác"
# What stays when a video's media is cleaned at level 1; level 2 also removes the MP4.
KEPT = {"Ảnh thu nhỏ"}
MP4_KINDS = {"MP4 cuối", "MP4 tải lên"}
LEVEL_1_DAYS = 30
LEVEL_2_DAYS = 60

_VIDEO_DIR = re.compile(r"videos/(\d+)/")


@dataclass
class Item:
    video_id: int
    kind: str
    size: int


@dataclass
class VideoState:
    """What the database says about one video: `last_post` is the latest time one of its posts went live, if any."""

    last_post: datetime | None
    open_post: bool = False


def kind_of(name: str) -> str:
    for prefix, kind in KINDS:
        if name.startswith(prefix):
            return kind
    return OTHER


def scan(root: Path) -> list[Item]:
    """Every file under `videos/<id>/` with its kind and size."""
    items: list[Item] = []
    base = root / "videos"
    if not base.is_dir():
        return items
    for path in base.glob("*/*"):
        if not path.is_file() or path.name.startswith(".") or not path.parent.name.isdigit():
            continue
        items.append(Item(int(path.parent.name), kind_of(path.name), path.stat().st_size))
    return items


def video_states(db: DbSession) -> dict[int, VideoState]:
    """Per video id: its last live post, and whether it still has a post that is not over (so it would never be cleaned)."""
    states = {video_id: VideoState(None) for video_id in db.scalars(select(Video.id))}
    live = db.execute(
        select(Publication.video_id, func.max(Publication.published_at))
        .where(Publication.video_id.is_not(None), Publication.status == "published")
        .group_by(Publication.video_id)
    )
    for video_id, last in live:
        if video_id in states:
            states[video_id].last_post = last
    open_posts = db.scalars(
        select(Publication.video_id).where(
            Publication.video_id.is_not(None),
            Publication.status.in_(("pending", "scheduled", "pending_link", "private")),
        )
    )
    for video_id in open_posts:
        if video_id in states:
            states[video_id].open_post = True
    return states


def _gb(size: int) -> str:
    return f"{size / 1024**3:.2f} GB" if size >= 1024**3 else f"{size / 1024**2:.1f} MB"


def build(items: list[Item], states: dict[int, VideoState], now: datetime) -> list[str]:
    """The report's lines. Cleanable figures are an upper bound: they ignore winners and videos pinned to keep."""
    total = sum(item.size for item in items)
    by_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_group: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    orphan = [0, 0]
    sizes: dict[int, int] = defaultdict(int)
    level1 = level2 = 0
    seen_1: set[int] = set()
    seen_2: set[int] = set()
    for item in items:
        by_kind[item.kind][0] += 1
        by_kind[item.kind][1] += item.size
        sizes[item.video_id] += item.size
        state = states.get(item.video_id)
        if state is None:
            orphan[0] += 1
            orphan[1] += item.size
            continue
        if state.last_post is None:
            group = "Chưa đăng"
        elif state.open_post:
            group = "Còn bài đang mở"
        else:
            days = (now - state.last_post).days
            group = (
                "Đăng trong 30 ngày"
                if days < LEVEL_1_DAYS
                else ("Đăng 30–60 ngày trước" if days < LEVEL_2_DAYS else "Đăng hơn 60 ngày trước")
            )
        by_group[group][0] += 1
        by_group[group][1] += item.size
        old = group in ("Đăng 30–60 ngày trước", "Đăng hơn 60 ngày trước")
        if old and item.kind not in KEPT and item.kind not in MP4_KINDS:
            level1 += item.size
            seen_1.add(item.video_id)
        if group == "Đăng hơn 60 ngày trước" and item.kind in MP4_KINDS:
            level2 += item.size
            seen_2.add(item.video_id)
    lines = [
        f"Tổng: {_gb(total)} trong {len(items)} file của {len(sizes)} thư mục video.",
        "",
        "Theo loại file:",
    ]
    for kind, (count, size) in sorted(by_kind.items(), key=lambda pair: -pair[1][1]):
        lines.append(f"  {kind}: {_gb(size)} ({count} file)")
    lines += ["", "Theo trạng thái đăng của video:"]
    for group in (
        "Chưa đăng",
        "Còn bài đang mở",
        "Đăng trong 30 ngày",
        "Đăng 30–60 ngày trước",
        "Đăng hơn 60 ngày trước",
    ):
        count, size = by_group.get(group, [0, 0])
        lines.append(f"  {group}: {_gb(size)} ({count} file)")
    lines.append(f"  Thư mục không còn video trong cơ sở dữ liệu: {_gb(orphan[1])} ({orphan[0]} file)")
    lines += [
        "",
        "Có thể giải phóng nếu bật luật (chặn trên, chưa trừ video thắng và video ghim giữ):",
        f"  Mức 1, file dựng của {len(seen_1)} video đăng quá 30 ngày: {_gb(level1)}",
        f"  Mức 2, thêm MP4 của {len(seen_2)} video đăng quá 60 ngày: {_gb(level2)}",
    ]
    biggest = sorted(sizes.items(), key=lambda pair: -pair[1])[:5]
    lines += ["", "5 video nặng nhất:"] + [f"  video {video_id}: {_gb(size)}" for video_id, size in biggest]
    return lines


def report(db: DbSession, root: Path, now: datetime) -> list[str]:
    return build(scan(root), video_states(db), now)


__all__ = ["Item", "VideoState", "build", "kind_of", "report", "scan"]
