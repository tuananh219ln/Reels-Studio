from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .errors import ApiError
from .models import Session, User
from .rules import RuleError, avatar_initial, check_password, clean_name, normalize_email
from .security import hash_password, verify_password
from .sessions import (
    clear_session_cookie,
    current_member,
    current_session,
    now,
    revoke_sessions,
    set_session_cookie,
    start_session,
)

router = APIRouter(prefix="/api")


class LoginBody(BaseModel):
    email: str
    password: str


class PasswordBody(BaseModel):
    current_password: str | None = None
    new_password: str


class NameBody(BaseModel):
    name: str


def me_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "initial": avatar_initial(user.name),
        "must_change_password": user.must_change_password,
    }


def rule_error(err: RuleError) -> ApiError:
    return ApiError(422, err.code, err.message)


@router.post("/auth/login")
def login(body: LoginBody, response: Response, db: DbSession = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == normalize_email(body.email)))
    if not verify_password(body.password, user.password_hash if user else None):
        raise ApiError(401, "invalid_credentials", "Email hoặc mật khẩu không đúng")
    # Only reveal that an account is disabled to someone who proved they own it.
    if not user.is_active:
        raise ApiError(403, "account_disabled", "Tài khoản đã bị vô hiệu hoá")
    token = start_session(db, user)
    user.last_login_at = now()
    db.commit()
    set_session_cookie(response, token)
    return me_payload(user)


@router.post("/auth/logout")
def logout(response: Response, session: Session = Depends(current_session), db: DbSession = Depends(get_db)) -> dict:
    db.delete(session)
    db.commit()
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(session: Session = Depends(current_session)) -> dict:
    return me_payload(session.user)


@router.patch("/me")
def rename(body: NameBody, session: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    try:
        name = clean_name(body.name)
    except RuleError as err:
        raise rule_error(err) from None
    user = session.user
    user.name = name
    db.commit()
    return me_payload(user)


@router.post("/me/password")
def change_password(
    body: PasswordBody, session: Session = Depends(current_session), db: DbSession = Depends(get_db)
) -> dict:
    user = session.user
    # The forced change after a temp password does not ask for the old one; the menu change does.
    if not user.must_change_password and not verify_password(body.current_password or "", user.password_hash):
        raise ApiError(400, "wrong_current_password", "Mật khẩu hiện tại không đúng")
    try:
        check_password(body.new_password)
    except RuleError as err:
        raise rule_error(err) from None
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    revoke_sessions(db, user.id, keep_session_id=session.id)
    db.commit()
    return me_payload(user)
