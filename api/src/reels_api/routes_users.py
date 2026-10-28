from fastapi import APIRouter, Depends
from psycopg.errors import DeadlockDetected, SerializationFailure
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .errors import ApiError
from .models import Session, User
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


def _last_active_error() -> ApiError:
    return ApiError(409, "last_active_user", "Phải còn ít nhất một người dùng đang hoạt động")


def _user_payload(user: User, active_sessions: int, me: Session) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "initial": avatar_initial(user.name),
        "is_active": user.is_active,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "active_sessions": active_sessions,
        "is_me": user.id == me.user_id,
    }


def _payload_for(db: DbSession, user: User, me: Session) -> dict:
    count = db.scalar(
        select(func.count()).select_from(Session).where(Session.user_id == user.id, Session.expires_at > now())
    )
    return _user_payload(user, count, me)


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
        pattern = f"%{q.strip()}%"
        query = query.where(or_(User.email.ilike(pattern), User.name.ilike(pattern)))
    return [_user_payload(user, count, me) for user, count in db.execute(query).all()]


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
def disable_user(user_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    user = _other_user(db, user_id, me, "Không thể vô hiệu hoá chính mình", "cannot_disable_self")
    try:
        # Lock every active user, not only the target: two people disabling each other at the same
        # moment then serialize, and the second one re-counts after the first has committed.
        active_ids = db.scalars(
            select(User.id).where(User.is_active).order_by(User.id).with_for_update()
        ).all()
        db.refresh(user)
        if user.is_active:
            if len(active_ids) <= 1:
                raise _last_active_error()
            user.is_active = False
            revoke_sessions(db, user.id)
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
    user.is_active = True
    db.commit()
    return _payload_for(db, user, me)


@router.post("/{user_id}/temp-password")
def set_temp_password(
    user_id: int, body: TempPasswordBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    user = _cannot_target_self(db, user_id, me)
    if not user.is_active:
        raise ApiError(409, "user_disabled", "Hãy kích hoạt lại người dùng trước")
    try:
        check_password(body.password)
    except RuleError as err:
        raise rule_error(err) from None
    user.password_hash = hash_password(body.password)
    user.must_change_password = True
    revoke_sessions(db, user.id)
    db.commit()
    return _payload_for(db, user, me)


@router.post("/{user_id}/sign-out-all")
def sign_out_all(user_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    user = _cannot_target_self(db, user_id, me)
    revoke_sessions(db, user.id)
    db.commit()
    return _payload_for(db, user, me)
