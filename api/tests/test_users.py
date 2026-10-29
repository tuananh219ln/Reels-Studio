from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from conftest import PASSWORD, client_for, expire_all_sessions, login, make_user
from reels_api.models import Session, User


@pytest.fixture
def me(client, db):
    user = make_user(db)
    login(client)
    return user


def add(client, email="binh@doi.vn", name="Trần Thị Bình", password="tam-thoi-123"):
    return client.post("/api/users", json={"email": email, "name": name, "password": password})


def row_for(client, email):
    return next(row for row in client.get("/api/users").json() if row["email"] == email)


def test_list_shows_every_column_and_marks_me(client, me):
    rows = client.get("/api/users").json()
    assert rows == [{
        "id": me.id, "email": "an@doi.vn", "name": "Nguyễn Văn An", "initial": "A", "is_active": True,
        "last_login_at": rows[0]["last_login_at"], "active_sessions": 1, "is_me": True,
    }]
    assert datetime.fromisoformat(rows[0]["last_login_at"]).tzinfo is not None


def test_new_user_has_no_last_login_and_no_sessions(client, me):
    add(client)
    row = row_for(client, "binh@doi.vn")
    assert (row["last_login_at"], row["active_sessions"], row["is_me"]) == (None, 0, False)


def test_search_matches_email_or_name_case_insensitively(client, me):
    add(client)
    assert [r["email"] for r in client.get("/api/users", params={"q": "BÌNH"}).json()] == ["binh@doi.vn"]
    assert [r["email"] for r in client.get("/api/users", params={"q": "AN@DOI"}).json()] == ["an@doi.vn"]
    assert client.get("/api/users", params={"q": "khong-co"}).json() == []


def test_search_treats_underscore_and_percent_literally(client, me):
    add(client, email="an_b@doi.vn", name="An B")
    add(client, email="anb@doi.vn", name="An C")
    assert [r["email"] for r in client.get("/api/users", params={"q": "an_"}).json()] == ["an_b@doi.vn"]
    assert client.get("/api/users", params={"q": "%"}).json() == []


def test_add_user_normalizes_email_flags_forced_change_and_records_creator(client, db, me):
    response = add(client, email="  Binh@Doi.VN ", name="  Trần Thị Bình ")
    assert response.status_code == 201
    user = db.scalar(select(User).where(User.email == "binh@doi.vn"))
    assert (user.name, user.must_change_password, user.is_active, user.created_by_id) == (
        "Trần Thị Bình", True, True, me.id)
    assert user.created_at is not None

    other = client_for(client.app)
    login(other, email="binh@doi.vn", password="tam-thoi-123")
    assert other.get("/api/me").json()["must_change_password"] is True


@pytest.mark.parametrize(
    ("body", "status", "code", "message"),
    [
        ({"email": "AN@doi.vn"}, 409, "email_exists", "Email này đã có trong hệ thống"),
        ({"email": "abc"}, 422, "invalid_email", "Email không hợp lệ"),
        ({"name": "   "}, 422, "invalid_name", "Tên phải từ 1 đến 60 ký tự"),
        ({"name": "x" * 61}, 422, "invalid_name", "Tên phải từ 1 đến 60 ký tự"),
        ({"password": "1234567"}, 422, "weak_password", "Mật khẩu phải có ít nhất 8 ký tự"),
    ],
)
def test_add_user_rejections(client, db, me, body, status, code, message):
    response = client.post("/api/users", json={"email": "binh@doi.vn", "name": "Bình", "password": "tam-thoi-123"} | body)
    assert response.status_code == status
    assert response.json() == {"code": code, "message": message}
    assert len(db.scalars(select(User)).all()) == 1


def test_disable_signs_the_user_out_and_blocks_login(app, client, db, me):
    user_id = add(client).json()["id"]
    target = client_for(app)
    login(target, email="binh@doi.vn", password="tam-thoi-123")

    response = client.post(f"/api/users/{user_id}/disable")

    assert response.status_code == 200
    assert (response.json()["is_active"], response.json()["active_sessions"]) == (False, 0)
    assert target.get("/api/me").status_code == 401
    refused = target.post("/api/auth/login", json={"email": "binh@doi.vn", "password": "tam-thoi-123"})
    assert refused.json()["code"] == "account_disabled"


def test_cannot_disable_yourself(client, db, me):
    response = client.post(f"/api/users/{me.id}/disable")
    assert response.status_code == 409
    assert response.json() == {"code": "cannot_disable_self", "message": "Không thể vô hiệu hoá chính mình"}
    db.refresh(me)
    assert me.is_active


def test_enable_keeps_password_and_forced_change_flag(app, client, db, me):
    user_id = add(client).json()["id"]
    client.post(f"/api/users/{user_id}/disable")

    response = client.post(f"/api/users/{user_id}/enable")

    assert response.json()["is_active"] is True
    other = client_for(app)
    login(other, email="binh@doi.vn", password="tam-thoi-123")
    assert other.get("/api/me").json()["must_change_password"] is True


def test_temp_password_signs_out_and_forces_a_change(app, client, db):
    make_user(db, email="binh@doi.vn", name="Bình")
    me = make_user(db)
    login(client)
    target = client_for(app)
    login(target, email="binh@doi.vn")
    binh = db.scalar(select(User).where(User.email == "binh@doi.vn"))

    response = client.post(f"/api/users/{binh.id}/temp-password", json={"password": "tam-moi-1234"})

    assert response.status_code == 200
    assert response.json()["active_sessions"] == 0
    assert target.get("/api/me").status_code == 401
    login(target, email="binh@doi.vn", password="tam-moi-1234")
    assert target.get("/api/me").json()["must_change_password"] is True
    assert me.is_active


def test_temp_password_rules(client, db, me):
    user_id = add(client).json()["id"]
    short = client.post(f"/api/users/{user_id}/temp-password", json={"password": "ngan"})
    assert (short.status_code, short.json()["code"]) == (422, "weak_password")

    client.post(f"/api/users/{user_id}/disable")
    disabled = client.post(f"/api/users/{user_id}/temp-password", json={"password": "tam-moi-1234"})
    assert disabled.status_code == 409
    assert disabled.json() == {"code": "user_disabled", "message": "Hãy kích hoạt lại người dùng trước"}


@pytest.mark.parametrize("action", ["temp-password", "sign-out-all"])
def test_cannot_target_yourself_through_the_api(client, db, me, action):
    response = client.post(f"/api/users/{me.id}/{action}", json={"password": "tam-moi-1234"})
    assert response.status_code == 409
    assert response.json() == {
        "code": "cannot_target_self", "message": "Không thể thực hiện thao tác này trên tài khoản của bạn"}
    assert client.get("/api/me").status_code == 200


def test_sign_out_all_devices(app, client, db, me):
    user_id = add(client).json()["id"]
    devices = [client_for(app), client_for(app)]
    for device in devices:
        login(device, email="binh@doi.vn", password="tam-thoi-123")
    assert row_for(client, "binh@doi.vn")["active_sessions"] == 2

    response = client.post(f"/api/users/{user_id}/sign-out-all")

    assert response.json()["active_sessions"] == 0
    assert all(device.get("/api/me").status_code == 401 for device in devices)


def test_session_count_ignores_expired_sessions(app, client, db, me):
    user_id = add(client).json()["id"]
    device = client_for(app)
    login(device, email="binh@doi.vn", password="tam-thoi-123")
    expire_all_sessions(db, user_id)
    assert row_for(client, "binh@doi.vn")["active_sessions"] == 0


def test_last_login_is_updated_on_each_login(app, client, db, me):
    add(client)
    device = client_for(app)
    login(device, email="binh@doi.vn", password="tam-thoi-123")
    first = row_for(client, "binh@doi.vn")["last_login_at"]
    binh = db.scalar(select(User).where(User.email == "binh@doi.vn"))
    binh.last_login_at = datetime.now(UTC) - timedelta(days=3)
    db.commit()
    login(device, email="binh@doi.vn", password="tam-thoi-123")
    assert datetime.fromisoformat(row_for(client, "binh@doi.vn")["last_login_at"]) >= datetime.fromisoformat(first)


@pytest.mark.parametrize("action", ["disable", "enable", "temp-password", "sign-out-all"])
def test_unknown_user_is_404(client, me, action):
    response = client.post(f"/api/users/999999/{action}", json={"password": "tam-moi-1234"})
    assert response.status_code == 404
    assert response.json()["code"] == "user_not_found"


def test_user_management_needs_a_session(app, db):
    anonymous = client_for(app)
    assert anonymous.get("/api/users").status_code == 401
    assert db.scalars(select(Session)).all() == []
