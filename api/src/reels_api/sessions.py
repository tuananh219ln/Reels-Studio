from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session as DbSession, joinedload

from .db import get_db
from .errors import ApiError
from .models import Session, User
from .security import hash_session_token, new_session_token

COOKIE_NAME = "reels_session"
SESSION_LIFETIME = timedelta(days=30)


def now() -> datetime:
    return datetime.now(UTC)


def set_session_cookie(response: Response, token: str) -> None:
    # Secure stays off: the app only runs over http on localhost until the HTTPS deploy spec.
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")


def start_session(db: DbSession, user: User) -> str:
    token = new_session_token()
    db.add(Session(user_id=user.id, token_hash=hash_session_token(token), expires_at=now() + SESSION_LIFETIME))
    return token


def revoke_sessions(db: DbSession, user_id: int, keep_session_id: int | None = None) -> None:
    query = delete(Session).where(Session.user_id == user_id)
    if keep_session_id is not None:
        query = query.where(Session.id != keep_session_id)
    db.execute(query)


def not_authenticated() -> ApiError:
    return ApiError(401, "not_authenticated", "Phiên đăng nhập đã hết hạn, hãy đăng nhập lại")


def current_session(request: Request, response: Response, db: DbSession = Depends(get_db)) -> Session:
    """Any valid session, including one that still has to change its password."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise not_authenticated()
    session = db.scalar(
        select(Session).where(Session.token_hash == hash_session_token(token)).options(joinedload(Session.user))
    )
    moment = now()
    if session is None or session.expires_at <= moment or not session.user.is_active:
        raise not_authenticated()
    # A plain UPDATE (not the ORM flush) so a session revoked by a concurrent request after the SELECT
    # simply matches no row and becomes a 401 instead of a stale-data error.
    renewed = db.execute(
        update(Session).where(Session.id == session.id).values(expires_at=moment + SESSION_LIFETIME)
    ).rowcount
    # Commit the renewal on its own before the endpoint runs, so no session-row lock is held while
    # an endpoint waits for user-row locks (two people disabling each other would otherwise deadlock).
    db.commit()
    if not renewed:
        raise not_authenticated()
    set_session_cookie(response, token)
    return session


def current_member(session: Session = Depends(current_session)) -> Session:
    """A session allowed to use the app: a pending forced password change blocks everything else."""
    if session.user.must_change_password:
        raise ApiError(403, "password_change_required", "Bạn cần đổi mật khẩu trước khi tiếp tục")
    return session
