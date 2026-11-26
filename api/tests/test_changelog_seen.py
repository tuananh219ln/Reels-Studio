"""'Có gì mới': each member's mark of the newest change they were shown (docs/decisions/2026-11-26-whats-new.md)."""

from datetime import UTC, datetime

from conftest import login, make_user


def test_a_new_member_has_seen_nothing(client, db):
    make_user(db)
    login(client)
    assert client.get("/api/me").json()["changelog_seen_at"] is None


def test_closing_the_window_keeps_the_newest_change_shown(client, db):
    user = make_user(db)
    login(client)

    response = client.put("/api/me/changelog-seen", json={"seen_at": "2026-11-26T09:56:51Z"})

    assert response.status_code == 200
    assert response.json()["changelog_seen_at"] == "2026-11-26T09:56:51+00:00"
    db.refresh(user)
    assert user.changelog_seen_at == datetime(2026, 11, 26, 9, 56, 51, tzinfo=UTC)
    assert client.get("/api/me").json()["changelog_seen_at"] == "2026-11-26T09:56:51+00:00"


def test_an_older_mark_never_brings_changes_back(client, db):
    make_user(db)
    login(client)
    client.put("/api/me/changelog-seen", json={"seen_at": "2026-11-26T09:56:51Z"})

    response = client.put("/api/me/changelog-seen", json={"seen_at": "2026-11-20T00:00:00Z"})

    assert response.json()["changelog_seen_at"] == "2026-11-26T09:56:51+00:00"


def test_each_member_has_their_own_mark(client, db):
    make_user(db)
    make_user(db, email="binh@doi.vn", name="Trần Bình")
    login(client)
    client.put("/api/me/changelog-seen", json={"seen_at": "2026-11-26T09:56:51Z"})

    client.post("/api/auth/logout")
    login(client, email="binh@doi.vn")

    assert client.get("/api/me").json()["changelog_seen_at"] is None


def test_marking_needs_a_session(client, db):
    response = client.put("/api/me/changelog-seen", json={"seen_at": "2026-11-26T09:56:51Z"})
    assert response.status_code == 401
