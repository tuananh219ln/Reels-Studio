"""One-off: video names that piled up copy suffixes ("A (copy) (copy) (xáo 2) (xáo 3)") keep one: "A (xáo 3)".

Run by hand as `python -m reels_api clean-video-names` (a dry run that prints every change), then again with
`--apply` once the list looks right. Names with no copy suffix, and "(bản N)" names, are left as they are."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .models import Video
from .videos import base_name

_PILED = re.compile(r"\((?:copy|xáo \d+)\)\s*$", re.IGNORECASE)
_SHUFFLE = re.compile(r"\(xáo (\d+)\)", re.IGNORECASE)


def cleaned(name: str) -> str:
    """The name with one suffix: the base, plus the last "(xáo N)" it had; a bare "(copy)" suffix is dropped."""
    base = base_name(name) or name
    shuffles = _SHUFFLE.findall(name)
    return f"{base} (xáo {shuffles[-1]})" if shuffles else base


def apply(db: DbSession, dry_run: bool = True) -> list[str]:
    lines = []
    for video in db.scalars(select(Video).where(Video.name.is_not(None)).order_by(Video.id)):
        if not _PILED.search(video.name):
            continue
        new = cleaned(video.name)
        if new == video.name:
            continue
        lines.append(f"{video.id} | {video.name} → {new}")
        if not dry_run:
            video.name = new
    if not dry_run:
        db.commit()
    lines.append(f"{len(lines)} tên {'sẽ đổi (chạy lại với --apply để ghi)' if dry_run else 'đã đổi'}")
    return lines
