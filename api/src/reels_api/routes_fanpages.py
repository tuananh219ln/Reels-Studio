"""Connecting Facebook Pages. A token only ever goes in: no response carries it, and every token is checked with
Facebook before it is kept."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from . import affiliate, auto_runs, facebook, fanpages, page_dashboard, plans
from .db import get_db
from .errors import ApiError
from .models import AffiliateAccount, Fanpage, FanpageFollowers, Session
from .routes_videos import invalid
from .sessions import current_member

router = APIRouter(prefix="/api/fanpages")

MAX_TOKEN_LENGTH = 1000


class TokenBody(BaseModel):
    token: str


class AddBody(TokenBody):
    page_ids: list[str]


class ActiveBody(BaseModel):
    active: bool


class AutoBody(BaseModel):
    """ "Bán tự động" on the Page's card; an absent field is left as it is."""

    auto_prepare: bool | None = None
    prepare_time: str | None = None
    tiktok_account_id: int | None = None
    tiktok_own_version: bool | None = None


class ShopeeAccountBody(BaseModel):
    account_id: int | None


def _clean_token(token: str) -> str:
    token = token.strip()
    if not token:
        raise invalid("Hãy dán token")
    if len(token) > MAX_TOKEN_LENGTH or len(token.split()) > 1:
        raise invalid("Token không hợp lệ, hãy chép lại đúng một dòng token")
    return token


def _pages_of(token: str) -> list[dict]:
    try:
        pages = facebook.managed_pages(token)
    except facebook.FacebookError as err:
        raise ApiError(422, "facebook_refused", err.message) from None
    if not pages:
        raise ApiError(
            422,
            "no_pages",
            "Token không quản lý Page nào: hãy gán Page cho tài khoản tạo token và cấp quyền pages_show_list",
        )
    return pages


def _shopee_account(db: DbSession, row: Fanpage, me: Session) -> dict | None:
    """The Page's Shopee account, shown only to the Page's owner: a member's affiliate accounts are their own."""
    if row.owner_id != me.user_id or row.shopee_account_id is None:
        return None
    account = db.get(AffiliateAccount, row.shopee_account_id)
    if account is None or account.owner_id != me.user_id:
        return None
    return {"id": account.id, "name": account.name, "usable": affiliate.credentials(account) is not None}


def _auto(db: DbSession, row: Fanpage, me: Session) -> dict | None:
    """ "Bán tự động", shown only to the Page's owner, who alone sets it and approves its videos."""
    if row.owner_id != me.user_id:
        return None
    return {
        "auto_prepare": row.auto_prepare,
        "prepare_time": row.prepare_time,
        "tiktok_account_id": row.tiktok_account_id,
        "tiktok_own_version": row.tiktok_own_version,
        "tiktok_problem": auto_runs.tiktok_account_problem(db, row) if row.tiktok_account_id else None,
    }


def _rows(db: DbSession, me: Session) -> list[dict]:
    rows = list(
        db.scalars(
            select(Fanpage)
            .options(joinedload(Fanpage.updated_by), joinedload(Fanpage.owner))
            .order_by(Fanpage.name, Fanpage.id)
        )
    )
    checks = fanpages.check_payload(db, rows)
    insights = fanpages.insights_summary(db, rows)
    scheduled = fanpages.scheduled_counts(db)
    posts = fanpages.post_counts(db)
    return [
        {
            "id": row.id,
            "page_id": row.page_id,
            "name": row.name,
            "token_tail": row.token_tail,
            "active": row.active,
            "updated_at": row.updated_at.isoformat(),
            "updated_by": row.updated_by.email if row.updated_by else None,
            "owner": {"id": row.owner.id, "name": row.owner.name} if row.owner else None,
            "mine": row.owner_id == me.user_id,
            "shopee_account": _shopee_account(db, row, me),
            "auto": _auto(db, row, me),
            "check": checks[row.id],
            "insights": insights[row.id],
            "scheduled_posts": scheduled.get(row.id, 0),
            # Every post ever made to the Page, cancelled and deleted ones too: a Page with any is kept for history.
            "posts": posts.get(row.id, 0),
        }
        for row in rows
    ]


def _fanpage(db: DbSession, fanpage_id: int) -> Fanpage:
    row = db.scalar(select(Fanpage).where(Fanpage.id == fanpage_id).with_for_update())
    if row is None:
        raise ApiError(404, "fanpage_not_found", "Không tìm thấy Fanpage")
    return row


@router.get("")
def list_fanpages(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    return _rows(db, me)


@router.post("/lookup")
def lookup(body: TokenBody, me: Session = Depends(current_member)) -> dict:
    """The Pages a pasted token manages, to choose from. Nothing is saved here."""
    pages = _pages_of(_clean_token(body.token))
    return {"pages": [{"page_id": page["id"], "name": page["name"], "can_post": page["can_post"]} for page in pages]}


@router.post("", status_code=201)
def add(body: AddBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    token = _clean_token(body.token)
    if not body.page_ids:
        raise invalid("Hãy chọn ít nhất một Page")
    usable = {page["id"]: page for page in _pages_of(token) if page["can_post"]}
    if not set(body.page_ids) <= set(usable):
        raise invalid("Token không có quyền đăng lên Page đã chọn")
    for page_id in dict.fromkeys(body.page_ids):
        fanpages.save(db, page_id, usable[page_id]["name"], usable[page_id]["token"], me.user_id)
    db.commit()
    return _rows(db, me)


@router.put("/{fanpage_id}/token")
def replace_token(
    fanpage_id: int, body: TokenBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> list[dict]:
    token = _clean_token(body.token)
    row = _fanpage(db, fanpage_id)
    page = next((page for page in _pages_of(token) if page["id"] == row.page_id and page["can_post"]), None)
    if page is None:
        raise invalid(f"Token mới không có quyền đăng lên Page “{row.name}”")
    fanpages.save(db, row.page_id, page["name"], page["token"], me.user_id)
    db.commit()
    return _rows(db, me)


@router.patch("/{fanpage_id}")
def set_active(
    fanpage_id: int, body: ActiveBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> list[dict]:
    row = _fanpage(db, fanpage_id)
    row.active, row.updated_by_id = body.active, me.user_id
    db.commit()
    return _rows(db, me)


@router.post("/{fanpage_id}/owner")
def claim(fanpage_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    """ "Nhận Page này": a Page that belongs to nobody becomes the member's. A Page that has an owner keeps it."""
    row = _fanpage(db, fanpage_id)
    if row.owner_id is not None and row.owner_id != me.user_id:
        raise ApiError(409, "page_has_owner", f"Fanpage “{row.name}” đã thuộc một thành viên khác")
    row.owner_id = me.user_id
    db.commit()
    return _rows(db, me)


@router.put("/{fanpage_id}/shopee-account")
def set_shopee_account(
    fanpage_id: int, body: ShopeeAccountBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> list[dict]:
    """The Shopee account whose links the Page's comments carry: one of its owner's own."""
    row = _fanpage(db, fanpage_id)
    if row.owner_id != me.user_id:
        raise ApiError(403, "not_page_owner", "Chỉ chủ của Fanpage mới gắn được tài khoản Shopee")
    if body.account_id is not None:
        account = db.get(AffiliateAccount, body.account_id)
        if account is None or account.owner_id != me.user_id or account.platform != "shopee":
            raise invalid("Hãy chọn một tài khoản Shopee của bạn")
        if not account.active:
            raise invalid(f"Tài khoản “{account.name}” đang ngừng dùng")
    row.shopee_account_id = body.account_id
    db.commit()
    return _rows(db, me)


@router.put("/{fanpage_id}/auto")
def set_auto(
    fanpage_id: int, body: AutoBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> list[dict]:
    """ "Bán tự động": the switch, the preparing time and the TikTok account of the Page, set by its owner only."""
    row = _fanpage(db, fanpage_id)
    if row.owner_id != me.user_id:
        raise ApiError(403, "not_page_owner", "Chỉ chủ của Fanpage mới bật được bán tự động")
    fields = body.model_fields_set
    if "prepare_time" in fields and body.prepare_time is not None:
        try:
            [row.prepare_time] = plans.check_post_times([body.prepare_time])
        except plans.PlanError:
            raise invalid("Giờ chuẩn bị phải có dạng HH:MM") from None
    if "tiktok_account_id" in fields:
        if body.tiktok_account_id is not None:
            account = db.get(AffiliateAccount, body.tiktok_account_id)
            if account is None or account.owner_id != me.user_id or account.platform != "tiktok":
                raise invalid("Hãy chọn một tài khoản TikTok của bạn")
        row.tiktok_account_id = body.tiktok_account_id
    if body.auto_prepare is not None:
        row.auto_prepare = body.auto_prepare
    if body.tiktok_own_version is not None:
        row.tiktok_own_version = body.tiktok_own_version
    db.commit()
    return _rows(db, me)


@router.post("/freshen")
def freshen(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Opening the page: the worker checks the Pages not checked lately; a request never calls Facebook."""
    asked = fanpages.ask_if_stale(db)
    db.commit()
    return {"asked": asked}


@router.post("/{fanpage_id}/check")
def check_now(fanpage_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    """ "Kiểm tra ngay": the worker checks the Page within seconds; a request never calls Facebook."""
    row = _fanpage(db, fanpage_id)
    if not row.active:
        raise invalid(f"Fanpage “{row.name}” đang ngừng dùng, hãy dùng lại trước khi kiểm tra")
    fanpages.request_check(row)
    db.commit()
    return _rows(db, me)


@router.get("/{fanpage_id}/insights")
def page_insights(
    fanpage_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> list[dict]:
    """The Page's daily numbers of the last 30 days, oldest first, with its followers that day when read."""
    if db.get(Fanpage, fanpage_id) is None:
        raise ApiError(404, "fanpage_not_found", "Không tìm thấy Fanpage")
    followers = dict(
        db.execute(
            select(FanpageFollowers.day, FanpageFollowers.followers).where(FanpageFollowers.fanpage_id == fanpage_id)
        ).all()
    )
    return [
        {
            "day": row.day.isoformat(),
            "views": row.views,
            "reach": row.reach,
            "engagements": row.engagements,
            "followers": followers.get(row.day),
        }
        for row in fanpages.insights_of(db, fanpage_id)
    ]


@router.get("/{fanpage_id}/dashboard")
def page_dashboard_view(
    fanpage_id: int, days: int = 28, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """One Page's dashboard for the last `days` days (7, 28 or 90), each figure against the period before it."""
    if days not in page_dashboard.PERIODS:
        raise invalid("Khoảng thời gian chỉ được là 7, 28 hoặc 90 ngày")
    row = db.get(Fanpage, fanpage_id)
    if row is None:
        raise ApiError(404, "fanpage_not_found", "Không tìm thấy Fanpage")
    return page_dashboard.dashboard(db, row, days)


@router.get("/{fanpage_id}/content")
def page_content_view(
    fanpage_id: int, days: int = 28, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """The dashboard's "Nội dung" tab: the app's posts to the Page that went live in the last `days` days."""
    if days not in page_dashboard.PERIODS:
        raise invalid("Khoảng thời gian chỉ được là 7, 28 hoặc 90 ngày")
    row = db.get(Fanpage, fanpage_id)
    if row is None:
        raise ApiError(404, "fanpage_not_found", "Không tìm thấy Fanpage")
    return page_dashboard.content(db, row, days)


@router.delete("/{fanpage_id}")
def delete_page(fanpage_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    """Remove a Page connected by mistake or never used, with its token and numbers. A Page in use is stopped first, so
    a slip of the mouse cannot remove it; a Page with posts is kept, since "Bài đăng", the medians and who posted what
    point to it."""
    row = _fanpage(db, fanpage_id)
    if row.active:
        raise ApiError(409, "fanpage_in_use", "Hãy ngừng dùng Fanpage trước khi xóa")
    posts = fanpages.post_counts(db).get(row.id, 0)
    if posts:
        raise ApiError(
            409,
            "fanpage_has_posts",
            f"Fanpage đã có {posts} bài đăng nên được giữ lại để xem lịch sử; cứ để ngừng dùng",
        )
    db.delete(row)
    db.commit()
    return _rows(db, me)
