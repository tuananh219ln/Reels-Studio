"""Two people disabling each other at the same moment, on real committed data and real connections."""

import threading

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from conftest import PASSWORD, WEB_ORIGIN, client_for, login
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
