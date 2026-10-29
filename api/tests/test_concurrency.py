"""Two people disabling each other at the same moment, on real committed data and real connections."""

import threading

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import sessionmaker

from conftest import PASSWORD, WEB_ORIGIN, client_for, login
from reels_api import routes_auth, sessions
from reels_api.db import get_db
from reels_api.main import create_app
from reels_api.models import Session, User
from reels_api.security import hash_password

ROUNDS = 20


@pytest.fixture
def committed_app(engine, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", WEB_ORIGIN)
    factory = sessionmaker(engine, expire_on_commit=False)

    def real_db():
        with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = real_db
    yield app, factory
    with factory() as db:
        db.execute(delete(Session))
        db.execute(delete(User))
        db.commit()


@pytest.mark.parametrize(
    ("change", "status"),
    [({"password_hash": hash_password("tam-moi-1234"), "must_change_password": True}, 401), ({"is_active": False}, 403)],
    ids=["temp-password", "disable"],
)
def test_login_racing_a_reset_never_creates_a_session(committed_app, monkeypatch, change, status):
    """A teammate resets or disables the account while Argon2 checks the old password."""
    app, factory = committed_app
    with factory() as db:
        victim = User(email="an@doi.vn", name="An", password_hash=hash_password(PASSWORD), is_active=True,
                      must_change_password=False)
        db.add(victim)
        db.commit()
    real_verify = routes_auth.verify_password

    def verify_then_reset(password, password_hash):
        ok = real_verify(password, password_hash)
        with factory() as other:
            other.execute(update(User).where(User.id == victim.id).values(**change))
            other.execute(delete(Session).where(Session.user_id == victim.id))
            other.commit()
        return ok

    monkeypatch.setattr(routes_auth, "verify_password", verify_then_reset)
    response = client_for(app).post("/api/auth/login", json={"email": "an@doi.vn", "password": PASSWORD})

    assert response.status_code == status
    with factory() as db:
        assert db.scalars(select(Session)).all() == []


def test_session_revoked_after_it_was_read_gives_401_not_500(committed_app, monkeypatch):
    """Another request revokes the session between the session lookup and its renewal."""
    app, factory = committed_app
    with factory() as db:
        db.add(User(email="an@doi.vn", name="An", password_hash=hash_password(PASSWORD), is_active=True,
                    must_change_password=False))
        db.commit()
    client = client_for(app)
    login(client, email="an@doi.vn")
    real_now = sessions.now

    def revoke_then_now():
        with factory() as other:
            other.execute(delete(Session))
            other.commit()
        return real_now()

    monkeypatch.setattr(sessions, "now", revoke_then_now)
    response = client.get("/api/me")

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_mutual_disable_always_leaves_one_active_user(committed_app):
    app, factory = committed_app
    for _ in range(ROUNDS):
        with factory() as db:
            db.execute(delete(Session))
            db.execute(delete(User))
            a = User(email="a@doi.vn", name="A", password_hash=hash_password(PASSWORD), is_active=True,
                     must_change_password=False)
            b = User(email="b@doi.vn", name="B", password_hash=hash_password(PASSWORD), is_active=True,
                     must_change_password=False)
            db.add_all([a, b])
            db.commit()
        clients = {"a": client_for(app), "b": client_for(app)}
        login(clients["a"], email="a@doi.vn")
        login(clients["b"], email="b@doi.vn")

        barrier = threading.Barrier(2)
        results = {}

        def disable(actor, target_id):
            barrier.wait()
            results[actor] = clients[actor].post(f"/api/users/{target_id}/disable")

        threads = [threading.Thread(target=disable, args=("a", b.id)),
                   threading.Thread(target=disable, args=("b", a.id))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        statuses = sorted(response.status_code for response in results.values())
        assert statuses in ([200, 401], [200, 409]), [r.text for r in results.values()]
        loser = next(r for r in results.values() if r.status_code != 200)
        if loser.status_code == 409:
            assert loser.json()["code"] == "last_active_user"
        with factory() as db:
            assert len(db.scalars(select(User).where(User.is_active)).all()) == 1
