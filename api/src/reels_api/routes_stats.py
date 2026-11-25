"""The "Thống kê" page: the Pages compared side by side (page_stats.py)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from . import page_dashboard, page_stats
from .db import get_db
from .models import Session
from .routes_videos import invalid
from .sessions import current_member

router = APIRouter(prefix="/api/stats")

MAX_PAGES = 30


@router.get("")
def stats_view(
    days: int = 28,
    platform: str = "facebook",
    page_ids: str | None = None,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """One row per Page for the last `days` days (7, 28 or 90). `page_ids` is a comma-separated list; left out it is
    every Page."""
    if days not in page_dashboard.PERIODS:
        raise invalid("Khoảng thời gian chỉ được là 7, 28 hoặc 90 ngày")
    if platform not in page_stats.PLATFORMS:
        raise invalid("Nền tảng chỉ được là facebook hoặc instagram")
    ids = None
    if page_ids is not None:
        try:
            ids = [int(part) for part in page_ids.split(",") if part.strip()]
        except ValueError:
            raise invalid("Danh sách Page không hợp lệ") from None
        if len(ids) > MAX_PAGES:
            raise invalid(f"Chỉ so sánh tối đa {MAX_PAGES} Page một lần")
    return page_stats.stats(db, days, platform, ids)
