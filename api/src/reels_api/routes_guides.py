"""In-app guides: the "Hướng dẫn" of a screen (docs/decisions/2026-11-25-in-app-guides.md). Markdown files in `guides/`,
shipped with the api, so a guide is changed in the same pull request as the feature it explains. A file may open with
`<!-- screen: affiliate -->` to say which screen shows it; its title is its first heading."""

import re
from pathlib import Path

from fastapi import APIRouter, Depends

from .errors import ApiError
from .models import Session
from .sessions import current_member

router = APIRouter(prefix="/api/guides")

GUIDES = Path(__file__).with_name("guides")
SCREEN = re.compile(r"^<!--\s*screen:\s*([a-z0-9-]+)\s*-->\s*\n")
TITLE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def _read() -> dict[str, dict]:
    found = {}
    for path in sorted(GUIDES.glob("*.md"), key=lambda one: one.stem):
        text = path.read_text(encoding="utf-8")
        marker = SCREEN.match(text)
        body = text[marker.end() :] if marker else text
        title = TITLE.search(body)
        found[path.stem] = {
            "slug": path.stem,
            "screen": marker.group(1) if marker else None,
            "title": title.group(1).strip() if title else path.stem,
            "body": body,
        }
    return found


@router.get("")
def list_guides(screen: str | None = None, me: Session = Depends(current_member)) -> list[dict]:
    """The guides of one screen (all when `screen` is left out), without their text."""
    return [
        {key: guide[key] for key in ("slug", "screen", "title")}
        for guide in _read().values()
        if screen is None or guide["screen"] == screen
    ]


@router.get("/{slug}")
def get_guide(slug: str, me: Session = Depends(current_member)) -> dict:
    guide = _read().get(slug)
    if guide is None:
        raise ApiError(404, "guide_not_found", "Không tìm thấy hướng dẫn này")
    return guide
