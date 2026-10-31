import hashlib
import logging
from datetime import UTC, datetime, timedelta

import pytest
from conftest import PASSWORD, client_for, expire_all_sessions, login, make_user
from sqlalchemy import select

from reels_api.models import Session, User
from reels_api.sessions import COOKIE_NAME

GENERIC = {"code": "invalid_credentials", "message": "Email hoặc mật khẩu không đúng"}


def test_login_sets_http_only_lax_cookie_for_30_days(client, db):
    user = make_user(db)
    response = login(client)
    cookie = response.headers["set-cookie"]
    assert f"{COOKIE_NAME}=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=2592000" in cookie
    assert "Secure" not in cookie
    assert response.json() == {
        "id": user.id, "email": "an@doi.vn", "name": "Nguyễn Văn An", "initial": "A", "must_change_password": False,
    }


def test_only_a_hash_of_the_session_token_is_stored(client, db):
    make_user(db)
    login(client)
    token = client.cookies[COOKIE_NAME]
    stored = db.scalars(select(Session.token_hash)).all()
    assert stored == [hashlib.sha256(token.encode()).hexdigest()]
    assert token not in stored


def test_login_normalizes_email_and_records_last_login(client, db):
    user = make_user(db)
    login(client, email="  AN@Doi.VN ")
    db.refresh(user)
    assert user.last_login_at is not None
    assert abs(user.last_login_at - datetime.now(UTC)) < timedelta(minutes=1)


@pytest.mark.parametrize(
    ("email", "password", "active"),
    [("an@doi.vn", "sai-mat-khau", True), ("khong-co@doi.vn", PASSWORD, True), ("an@doi.vn", "sai-mat-khau", False)],
    ids=["wrong-password", "unknown-email", "disabled-wrong-password"],
)
def test_failed_login_gives_the_same_generic_message(client, db, email, password, active):
    make_user(db, active=active)
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401
    assert response.json() == GENERIC
    assert COOKIE_NAME not in client.cookies


def test_disabled_account_is_named_only_with_the_right_password(client, db):
    make_user(db, active=False)
    response = client.post("/api/auth/login", json={"email": "an@doi.vn", "password": PASSWORD})
    assert response.status_code == 403
    assert response.json() == {"code": "account_disabled", "message": "Tài khoản đã bị vô hiệu hoá"}
    assert db.scalars(select(Session)).all() == []


def test_requests_without_or_with_an_unknown_session_are_401(client, db):
    assert client.get("/api/me").status_code == 401
    client.cookies.set(COOKIE_NAME, "khong-ton-tai")
    response = client.get("/api/me")
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_expired_session_is_401(client, db):
    user = make_user(db)
    login(client)
    expire_all_sessions(db, user.id)
    assert client.get("/api/me").status_code == 401


def test_each_request_extends_the_session_by_30_days(client, db):
    user = make_user(db)
    login(client)
    session = db.scalar(select(Session).where(Session.user_id == user.id))
    session.expires_at = datetime.now(UTC) + timedelta(days=1)
    db.commit()

    response = client.get("/api/me")

    assert response.status_code == 200
    db.refresh(session)
    assert session.expires_at > datetime.now(UTC) + timedelta(days=29)
    assert "Max-Age=2592000" in response.headers["set-cookie"]


def test_logout_revokes_the_current_session(client, db):
    make_user(db)
    login(client)
    token = client.cookies[COOKIE_NAME]
    assert client.post("/api/auth/logout").status_code == 200
    client.cookies.set(COOKIE_NAME, token)
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize("origin", [None, "http://evil.example", "http://localhost:3100"])
def test_state_changing_requests_need_an_allowed_origin(app, db, origin):
    make_user(db)
    client = client_for(app)
    headers = {"Origin": origin} if origin else {}
    if origin is None:
        client.headers.pop("Origin")
    response = client.post("/api/auth/login", json={"email": "an@doi.vn", "password": PASSWORD}, headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "origin_not_allowed"
    assert db.scalars(select(Session)).all() == []
    assert db.scalar(select(User.last_login_at)) is None


@pytest.mark.parametrize("origin", [None, "http://evil.example"])
def test_patch_needs_an_allowed_origin_too(app, db, origin):
    make_user(db)
    client = client_for(app)
    login(client)
    client.headers.pop("Origin")
    headers = {"Origin": origin} if origin else {}
    response = client.patch("/api/me", json={"name": "Tên lạ"}, headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "origin_not_allowed"
    assert db.scalar(select(User.name)) == "Nguyễn Văn An"


def test_reads_do_not_need_an_origin(app, db):
    make_user(db)
    client = client_for(app)
    login(client)
    client.headers.pop("Origin")
    assert client.get("/api/me").status_code == 200


def test_malformed_body_does_not_echo_the_password(client):
    response = client.post("/api/auth/login", json={"password": "bi-mat-123456"})
    assert response.status_code == 422
    assert response.json() == {"code": "invalid_request", "message": "Dữ liệu gửi lên không hợp lệ"}
    assert "bi-mat-123456" not in response.text


def test_passwords_never_reach_responses_or_logs(client, db, caplog):
    caplog.set_level(logging.DEBUG)
    make_user(db)
    secrets = [PASSWORD, "tam-thoi-123", "moi-hoan-toan-1", "doi-tiep-456"]
    responses = [login(client)]
    created = client.post("/api/users", json={"email": "binh@doi.vn", "name": "Bình", "password": secrets[1]})
    responses.append(created)
    responses.append(client.post(f"/api/users/{created.json()['id']}/temp-password", json={"password": secrets[2]}))
    responses.append(client.post("/api/me/password", json={"current_password": PASSWORD, "new_password": secrets[3]}))
    responses.append(client.post("/api/auth/login", json={"email": "an@doi.vn", "password": "sai-hoan-toan"}))

    assert [r.status_code for r in responses] == [200, 201, 200, 200, 401]
    for secret in [*secrets, "sai-hoan-toan"]:
        assert all(secret not in r.text for r in responses)
        assert secret not in caplog.text
