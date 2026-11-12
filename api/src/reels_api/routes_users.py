from fastapi import APIRouter, Depends
from psycopg.errors import DeadlockDetected, SerializationFailure
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session as DbSession

from . import edit_log
from .db import get_db
from .errors import ApiError
from .models import EditLog, EditTemplate, Fanpage, KnowledgeTopic, Session, TopicPlanItem, User
from .routes_auth import rule_error
from .rules import RuleError, avatar_initial, check_password, clean_email, clean_name
from .security import hash_password
from .sessions import current_member, now, revoke_sessions

router = APIRouter(prefix="/api/users")


class NewUserBody(BaseModel):
    email: str
    name: str
    password: str


class TempPasswordBody(BaseModel):
    password: str


class DisableBody(BaseModel):
    # "Chuyển quyền sở hữu cho…": the active member who takes the disabled one's Pages, groups, ideas and templates.
    transfer_to: int | None = None


def _action(entry: EditLog | None) -> dict | None:
    """The row's "last action" line: what was done to the member, by whom and when (edit_log.USER)."""
    if entry is None:
        return None
    if "temp_password" in entry.changes:
        action = "temp_password"
    else:
        action = "enable" if (entry.changes.get("is_active") or {}).get("new") else "disable"
    return {"action": action, "by": entry.user.name if entry.user else None, "at": entry.created_at.isoformat()}


def _log(db: DbSession, user: User, me: Session, changes: dict) -> None:
    edit_log.record(db, edit_log.USER, user.id, "update", me.user_id, label=user.name, changes=changes)


def _hand_on(db: DbSession, user: User, to: User) -> str:
    """Moves the member's Pages, topic groups, plan ideas and templates to `to`; says what moved. A Page drops its
    Shopee account, which was the old owner's, for the new owner to set."""
    counts = []
    pages = db.execute(
        update(Fanpage).where(Fanpage.owner_id == user.id).values(owner_id=to.id, shopee_account_id=None)
    ).rowcount
    counts.append((pages, "Page"))
    for model, name in ((KnowledgeTopic, "nhóm chủ đề"), (TopicPlanItem, "ý tưởng"), (EditTemplate, "mẫu dựng")):
        moved = db.execute(update(model).where(model.created_by_id == user.id).values(created_by_id=to.id)).rowcount
        counts.append((moved, name))
    held = ", ".join(f"{count} {name}" for count, name in counts if count)
    return f"{held or 'Không có gì'} cho {to.name}"


def _last_active_error() -> ApiError:
    return ApiError(409, "last_active_user", "Phải còn ít nhất một người dùng đang hoạt động")


def _user_payload(user: User, active_sessions: int, me: Session, last: EditLog | None = None) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "initial": avatar_initial(user.name),
        "is_active": user.is_active,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "active_sessions": active_sessions,
        "is_me": user.id == me.user_id,
        "last_action": _action(last),
    }


def _payload_for(db: DbSession, user: User, me: Session) -> dict:
    count = db.scalar(
        select(func.count()).select_from(Session).where(Session.user_id == user.id, Session.expires_at > now())
    )
    return _user_payload(user, count, me, edit_log.last_edits(db, edit_log.USER).get(user.id))


def _other_user(db: DbSession, user_id: int, me: Session, self_message: str, self_code: str) -> User:
    if user_id == me.user_id:
        raise ApiError(409, self_code, self_message)
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, "user_not_found", "Không tìm thấy người dùng")
    return user


def _cannot_target_self(db: DbSession, user_id: int, me: Session) -> User:
    return _other_user(db, user_id, me, "Không thể thực hiện thao tác này trên tài khoản của bạn", "cannot_target_self")


@router.get("")
def list_users(q: str = "", me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    active_sessions = (
        select(Session.user_id, func.count().label("n"))
        .where(Session.expires_at > now())
        .group_by(Session.user_id)
        .subquery()
    )
    query = (
        select(User, func.coalesce(active_sessions.c.n, 0))
        .outerjoin(active_sessions, active_sessions.c.user_id == User.id)
        .order_by(User.created_at, User.id)
    )
    if q.strip():
        # Plain substring search: "_" and "%" typed by the user are literal characters, not wildcards.
        literal = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{literal}%"
        query = query.where(or_(User.email.ilike(pattern, escape="\\"), User.name.ilike(pattern, escape="\\")))
    last = edit_log.last_edits(db, edit_log.USER)
    return [_user_payload(user, count, me, last.get(user.id)) for user, count in db.execute(query).all()]


@router.post("", status_code=201)
def create_user(body: NewUserBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    try:
        email = clean_email(body.email)
        name = clean_name(body.name)
        check_password(body.password)
    except RuleError as err:
        raise rule_error(err) from None
    email_taken = ApiError(409, "email_exists", "Email này đã có trong hệ thống")
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise email_taken
    user = User(
        email=email,
        name=name,
        password_hash=hash_password(body.password),
        must_change_password=True,
        is_active=True,
        created_by_id=me.user_id,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        raise email_taken from None
    return _user_payload(user, 0, me)


@router.post("/{user_id}/disable")
def disable_user(
    user_id: int,
    body: DisableBody | None = None,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    user = _other_user(db, user_id, me, "Không thể vô hiệu hoá chính mình", "cannot_disable_self")
    to = None
    if body is not None and body.transfer_to is not None:
        to = db.get(User, body.transfer_to)
        if to is None or not to.is_active or to.id == user.id:
            raise ApiError(422, "invalid_value", "Hãy chọn một thành viên khác đang hoạt động để nhận")
    try:
        # Lock every active user, not only the target: two people disabling each other at the same
        # moment then serialize, and the second one re-counts after the first has committed.
        active_ids = db.scalars(select(User.id).where(User.is_active).order_by(User.id).with_for_update()).all()
        db.refresh(user)
        if user.is_active:
            if len(active_ids) <= 1:
                raise _last_active_error()
            user.is_active = False
            revoke_sessions(db, user.id)
            changes = {"is_active": {"old": True, "new": False}}
            if to is not None:
                changes["transfer"] = {"old": None, "new": _hand_on(db, user, to)}
            _log(db, user, me, changes)
        db.commit()
    except DBAPIError as err:
        db.rollback()
        if isinstance(err.orig, (DeadlockDetected, SerializationFailure)):
            raise _last_active_error() from None
        raise
    except ApiError:
        db.rollback()
        raise
    return _payload_for(db, user, me)


@router.post("/{user_id}/enable")
def enable_user(user_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, "user_not_found", "Không tìm thấy người dùng")
    if not user.is_active:
        user.is_active = True
        _log(db, user, me, {"is_active": {"old": False, "new": True}})
    db.commit()
    return _payload_for(db, user, me)


@router.post("/{user_id}/temp-password")
def set_temp_password(
    user_id: int, body: TempPasswordBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    _cannot_target_self(db, user_id, me)
    # Lock before checking is_active, so a disable committing meanwhile is seen rather than overwritten.
    user = db.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))
    # Only a disabled account (2026-11-09): recovering a teammate's account is disable, set, enable, each kept with
    # who did it, so an active member's password is never taken over quietly.
    if user.is_active:
        raise ApiError(
            409,
            "user_active",
            "Chỉ đặt mật khẩu tạm cho tài khoản đã vô hiệu hoá: hãy vô hiệu hoá, đặt mật khẩu tạm rồi kích hoạt lại",
        )
    try:
        check_password(body.password)
    except RuleError as err:
        raise rule_error(err) from None
    user.password_hash = hash_password(body.password)
    user.must_change_password = True
    revoke_sessions(db, user.id)
    _log(db, user, me, {"temp_password": {"old": None, "new": "đã đặt"}})
    db.commit()
    return _payload_for(db, user, me)


@router.post("/{user_id}/sign-out-all")
def sign_out_all(user_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    user = _cannot_target_self(db, user_id, me)
    revoke_sessions(db, user.id)
    db.commit()
    return _payload_for(db, user, me)
