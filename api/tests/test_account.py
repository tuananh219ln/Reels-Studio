from sqlalchemy import func, select

from conftest import PASSWORD, client_for, login, make_user
from reels_api.models import Session
from reels_api.sessions import COOKIE_NAME

FORCED = {"code": "password_change_required", "message": "Bạn cần đổi mật khẩu trước khi tiếp tục"}


def session_count(db, user_id):
    return db.scalar(select(func.count()).select_from(Session).where(Session.user_id == user_id))


class TestForcedChange:
    def test_flagged_session_can_only_read_me_change_password_and_logout(self, client, db):
        make_user(db, must_change=True)
        login(client)

        me = client.get("/api/me")
        assert me.status_code == 200
        assert me.json()["must_change_password"] is True
        for response in (client.get("/api/users"), client.patch("/api/me", json={"name": "Tên mới"}),
                         client.post("/api/users", json={"email": "x@doi.vn", "name": "X", "password": "12345678"})):
            assert response.status_code == 403
            assert response.json() == FORCED
        assert client.post("/api/auth/logout").status_code == 200

    def test_forced_change_needs_no_current_password_and_clears_the_flag(self, client, db):
        make_user(db, must_change=True)
        login(client)
        response = client.post("/api/me/password", json={"new_password": "moi-hoan-toan-1"})
        assert response.status_code == 200
        assert response.json()["must_change_password"] is False
        assert client.get("/api/users").status_code == 200
        client.post("/api/auth/logout")
        login(client, password="moi-hoan-toan-1")

    def test_forced_change_signs_out_other_sessions_but_keeps_this_one(self, app, db):
        user = make_user(db, must_change=True)
        other, this = client_for(app), client_for(app)
        login(other)
        login(this)

        this.post("/api/me/password", json={"new_password": "moi-hoan-toan-1"})

        assert session_count(db, user.id) == 1
        assert this.get("/api/me").status_code == 200
        assert other.get("/api/me").status_code == 401

    def test_forced_change_still_requires_eight_characters(self, client, db):
        make_user(db, must_change=True)
        login(client)
        response = client.post("/api/me/password", json={"new_password": "ngan"})
        assert response.status_code == 422
        assert response.json() == {"code": "weak_password", "message": "Mật khẩu phải có ít nhất 8 ký tự"}
        assert client.get("/api/me").json()["must_change_password"] is True


class TestMenuPasswordChange:
    def test_wrong_current_password_is_rejected(self, client, db):
        make_user(db)
        login(client)
        response = client.post("/api/me/password", json={"current_password": "sai-mat-khau", "new_password": "moi-12345"})
        assert response.status_code == 400
        assert response.json() == {"code": "wrong_current_password", "message": "Mật khẩu hiện tại không đúng"}
        client.post("/api/auth/logout")
        login(client)  # old password still works

    def test_missing_current_password_is_rejected(self, client, db):
        make_user(db)
        login(client)
        response = client.post("/api/me/password", json={"new_password": "moi-12345"})
        assert response.status_code == 400

    def test_short_new_password_is_rejected(self, client, db):
        make_user(db)
        login(client)
        response = client.post("/api/me/password", json={"current_password": PASSWORD, "new_password": "ngan"})
        assert response.status_code == 422
        assert response.json()["code"] == "weak_password"

    def test_change_signs_out_other_sessions_but_keeps_this_one(self, app, db):
        user = make_user(db)
        other, this = client_for(app), client_for(app)
        login(other)
        login(this)

        response = this.post("/api/me/password", json={"current_password": PASSWORD, "new_password": "moi-12345"})

        assert response.status_code == 200
        assert session_count(db, user.id) == 1
        assert this.get("/api/me").status_code == 200
        assert other.get("/api/me").status_code == 401
        assert COOKIE_NAME in this.cookies


class TestRename:
    def test_name_is_trimmed_and_initial_follows(self, client, db):
        make_user(db)
        login(client)
        response = client.patch("/api/me", json={"name": "  Trần Thị Bình  "})
        assert response.status_code == 200
        assert (response.json()["name"], response.json()["initial"]) == ("Trần Thị Bình", "B")
        assert client.get("/api/me").json()["name"] == "Trần Thị Bình"

    def test_invalid_names(self, client, db):
        make_user(db)
        login(client)
        for name in ("", "    ", "x" * 61):
            response = client.patch("/api/me", json={"name": name})
            assert response.status_code == 422
            assert response.json() == {"code": "invalid_name", "message": "Tên phải từ 1 đến 60 ký tự"}
        assert client.get("/api/me").json()["name"] == "Nguyễn Văn An"
