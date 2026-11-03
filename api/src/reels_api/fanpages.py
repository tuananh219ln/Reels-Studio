"""The team's Facebook Pages, connected on /fanpages, and the worker's check of each one.

Tokens are encrypted with the storage folder's key (see crypto.py).

The check (`check`) reads the Page with its own token, so a token that stopped working (its maker changed their password
or lost the Page) shows on /fanpages before a post fails on it. It also keeps the Page's current name and its followers,
one number per day, for the gain of the week. Like reading a post's numbers (metrics.py) it is not a job: the worker
checks a few due Pages between jobs, and a request never calls Facebook; "Kiểm tra ngay" only asks the worker.

A Page is due when it was never checked (just connected, or given a new token), `EVERY` after its last check, or when a
member asked. A failed check is recorded and waits like any other, so a broken token never loops.
"""

import logging
from datetime import timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload, sessionmaker

from . import analytics, crypto, facebook
from .facebook import FacebookError, Page
from .models import Fanpage, FanpageFollowers, FanpageInsights, Publication
from .sessions import now

log = logging.getLogger("reels_api.fanpages")

TOKEN_TAIL = 4
EVERY = timedelta(hours=12)
# Opening "Kết nối Fanpage" asks for a check of a Page whose last one is older than this.
ON_OPEN = timedelta(minutes=15)
# Page Insights days re-read at each check: Facebook revises its last days for a while.
INSIGHTS_DAYS = 7
# Pages checked per round of the worker; with INSIGHTS_TIMEOUT a dead Facebook holds the queue ~30 s at most.
BATCH = 3


def save(db: DbSession, page_id: str, name: str, token: str, user_id: int) -> Fanpage:
    """Connect a Page, or give a connected one its new token. Either way it is in use afterwards, and checked again
    soon: the last check said nothing about this token."""
    row = db.scalar(select(Fanpage).where(Fanpage.page_id == page_id))
    if row is None:
        row = Fanpage(page_id=page_id)
        db.add(row)
    row.name, row.active, row.updated_by_id = name, True, user_id
    row.token_encrypted = crypto.encrypt(token)
    row.token_tail = token[-TOKEN_TAIL:]
    row.checked_at = row.check_error = None
    return row


def in_use(db: DbSession) -> list[Fanpage]:
    query = select(Fanpage).options(joinedload(Fanpage.updated_by)).where(Fanpage.active.is_(True))
    return list(db.scalars(query.order_by(Fanpage.name, Fanpage.id)))


def load_page(db: DbSession, fanpage_id: int | None) -> Page:
    row = db.get(Fanpage, fanpage_id) if fanpage_id is not None else None
    if row is None:
        raise FacebookError("Video chưa chọn Fanpage, hãy chọn Fanpage rồi đăng lại")
    if not row.active:
        raise FacebookError(f"Fanpage “{row.name}” đang ngừng dùng, hãy dùng lại trong Kết nối Fanpage")
    return _page(row)


def _page(row: Fanpage) -> Page:
    try:
        return Page(row.page_id, crypto.decrypt(row.token_encrypted))
    except crypto.CannotDecrypt:
        raise FacebookError(f"Không đọc được token của “{row.name}”, hãy dán token mới trong Kết nối Fanpage") from None


# The worker's check


def _asked():
    return and_(
        Fanpage.check_requested_at.is_not(None),
        or_(Fanpage.checked_at.is_(None), Fanpage.checked_at < Fanpage.check_requested_at),
    )


def ask_if_stale(db: DbSession) -> int:
    """Opening "Kết nối Fanpage": ask for a check of each Page in use not checked for `ON_OPEN`, unless one is already
    asked for. A Page never checked is due anyway. Returns how many were asked; the caller commits."""
    rows = db.scalars(
        select(Fanpage).where(
            Fanpage.active.is_(True),
            Fanpage.checked_at.is_not(None),
            Fanpage.checked_at <= now() - ON_OPEN,
            ~_asked(),
        )
    ).all()
    for row in rows:
        request_check(row)
    return len(rows)


def due_checks(db: DbSession, limit: int = BATCH) -> list[Fanpage]:
    """The Pages to check now: asked for first, then the longest unchecked."""
    asked = _asked()
    query = (
        select(Fanpage)
        .where(
            Fanpage.active.is_(True),
            or_(asked, Fanpage.checked_at.is_(None), Fanpage.checked_at <= now() - EVERY),
        )
        .order_by(asked.desc(), Fanpage.checked_at.asc().nulls_first(), Fanpage.id)
        .limit(limit)
    )
    return list(db.scalars(query))


def check(db: DbSession, row: Fanpage) -> None:
    """Read the Page once with its token and record what came back. Commits.

    Written with an UPDATE that keeps `updated_at` as it is: "Cập nhật" on /fanpages is a member's change, not this."""
    at = now()
    values: dict = {"checked_at": at, "check_error": None, "updated_at": Fanpage.updated_at}
    try:
        page = _page(row)
        info = facebook.page_info(page)
    except FacebookError as err:
        values["check_error"] = err.message
        log.warning("Fanpage %s failed its check: %s %s", row.id, err.message, err.detail)
    else:
        if info["name"]:
            values["name"] = info["name"][:200]
        if info["followers"] is not None:
            values["followers_count"] = info["followers"]
            day = at.astimezone(analytics.VIETNAM).date()
            db.execute(
                insert(FanpageFollowers)
                .values(fanpage_id=row.id, day=day, followers=info["followers"])
                .on_conflict_do_update(index_elements=["fanpage_id", "day"], set_={"followers": info["followers"]})
            )
        values["insights_error"] = read_insights(db, row, page, at)
    db.execute(update(Fanpage).where(Fanpage.id == row.id).values(**values))
    db.commit()
    db.refresh(row)


def read_insights(db: DbSession, row: Fanpage, page: Page, at) -> str | None:
    """Keep the Page's daily numbers of the last `INSIGHTS_DAYS` days, rewritten each check since Facebook revises its
    recent days. Returns what went wrong (None when all of it was read); a token that works but lacks `read_insights`
    is not a broken connection, so this never sets `check_error`."""
    try:
        days, problems = facebook.page_insights(page, at - timedelta(days=INSIGHTS_DAYS), at)
    except FacebookError as err:
        return err.message
    for day, numbers in days.items():
        db.execute(
            insert(FanpageInsights)
            .values(fanpage_id=row.id, day=day, **numbers)
            .on_conflict_do_update(index_elements=["fanpage_id", "day"], set_=numbers)
        )
    return "; ".join(problems) or None


def insights_of(db: DbSession, fanpage_id: int, days: int = 30) -> list[FanpageInsights]:
    since = now().astimezone(analytics.VIETNAM).date() - timedelta(days=days)
    query = (
        select(FanpageInsights)
        .where(FanpageInsights.fanpage_id == fanpage_id, FanpageInsights.day > since)
        .order_by(FanpageInsights.day)
    )
    return list(db.scalars(query))


def check_due(factory: sessionmaker) -> None:
    """One round of the worker. Nothing here may stop the queue: a failure is logged and the next round goes on."""
    try:
        with factory() as db:
            ids = [row.id for row in due_checks(db)]
    except Exception:
        log.exception("Could not look for Fanpages to check")
        return
    for fanpage_id in ids:
        try:
            with factory() as db:
                row = db.get(Fanpage, fanpage_id)
                if row is not None:
                    check(db, row)
        except Exception:
            log.exception("Could not check Fanpage %s", fanpage_id)


# What /fanpages shows


def check_payload(db: DbSession, rows: list[Fanpage]) -> dict[int, dict]:
    """Each Page's last check, by fanpage id. `followers_this_week` counts from the last number read before this week's
    Monday (Vietnam time, as analytics.week_start), so it is None until the Page has one from last week."""
    monday = analytics.week_start(now()).astimezone(analytics.VIETNAM).date()
    last_day = (
        select(FanpageFollowers.fanpage_id, func.max(FanpageFollowers.day).label("day"))
        .where(FanpageFollowers.day < monday)
        .group_by(FanpageFollowers.fanpage_id)
        .subquery()
    )
    before = dict(
        db.execute(
            select(FanpageFollowers.fanpage_id, FanpageFollowers.followers).join(
                last_day,
                and_(FanpageFollowers.fanpage_id == last_day.c.fanpage_id, FanpageFollowers.day == last_day.c.day),
            )
        ).all()
    )
    result = {}
    for row in rows:
        start = before.get(row.id)
        asked = row.check_requested_at
        result[row.id] = {
            "checked_at": row.checked_at.isoformat() if row.checked_at else None,
            "error": row.check_error,
            "pending": row.active and (row.checked_at is None or (asked is not None and row.checked_at < asked)),
            "followers": row.followers_count,
            "followers_this_week": row.followers_count - start
            if row.followers_count is not None and start is not None
            else None,
        }
    return result


def insights_summary(db: DbSession, rows: list[Fanpage]) -> dict[int, dict]:
    """Each Page's views, reach and engagements summed over its last 7 days with numbers, and the last reading's
    error. A sum is None when no day had that number."""
    since = now().astimezone(analytics.VIETNAM).date() - timedelta(days=7)
    query = (
        select(
            FanpageInsights.fanpage_id,
            func.sum(FanpageInsights.views),
            func.sum(FanpageInsights.reach),
            func.sum(FanpageInsights.engagements),
        )
        .where(FanpageInsights.day > since)
        .group_by(FanpageInsights.fanpage_id)
    )
    sums = {fanpage_id: (views, reach, engagements) for fanpage_id, views, reach, engagements in db.execute(query)}
    result = {}
    for row in rows:
        views, reach, engagements = sums.get(row.id, (None, None, None))
        result[row.id] = {
            "last_7_days": {
                "views": int(views) if views is not None else None,
                "reach": int(reach) if reach is not None else None,
                "engagements": int(engagements) if engagements is not None else None,
            },
            "error": row.insights_error,
        }
    return result


def scheduled_counts(db: DbSession) -> dict[int, int]:
    """Each Page's posts still waiting for their time on Facebook: what a broken token puts at risk."""
    query = (
        select(Publication.fanpage_id, func.count())
        .where(Publication.status == "scheduled", Publication.scheduled_at > now())
        .group_by(Publication.fanpage_id)
    )
    return {fanpage_id: count for fanpage_id, count in db.execute(query) if fanpage_id is not None}


def post_counts(db: DbSession) -> dict[int, int]:
    query = select(Publication.fanpage_id, func.count()).group_by(Publication.fanpage_id)
    return {fanpage_id: count for fanpage_id, count in db.execute(query) if fanpage_id is not None}


def request_check(row: Fanpage) -> None:
    row.check_requested_at = now()
