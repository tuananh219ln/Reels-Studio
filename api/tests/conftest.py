from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DbSession

from reels_api.config import read_env
from reels_api.db import get_db
from reels_api.main import create_app
from reels_api.models import User
from reels_api.security import hash_password

API_DIR = Path(__file__).resolve().parents[1]
WEB_ORIGIN = "http://localhost:3000"
PASSWORD = "mat-khau-dung-1"


def _test_engine():
    url = read_env("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Chưa cấu hình TEST_DATABASE_URL (xem .env.example)")
    engine = create_engine(url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect():
            pass
    except OperationalError:
        pytest.skip("Không kết nối được Postgres test: chạy docker compose up -d postgres")
    return engine


@pytest.fixture(scope="session")
def engine():
    engine = _test_engine()
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))
    config.attributes["configure_logger"] = False
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    """Each test runs inside one outer transaction that is rolled back; the code's commits become savepoints."""
    connection = engine.connect()
    outer = connection.begin()
    session = DbSession(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()
    outer.rollback()
    connection.close()


@pytest.fixture
def app(db, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", WEB_ORIGIN)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return app


def client_for(app) -> TestClient:
    return TestClient(app, headers={"Origin": WEB_ORIGIN})


@pytest.fixture
def client(app):
    return client_for(app)


def make_user(db, email="an@doi.vn", name="Nguyễn Văn An", password=PASSWORD, must_change=False, active=True) -> User:
    user = User(email=email, name=name, password_hash=hash_password(password),
                must_change_password=must_change, is_active=active)
    db.add(user)
    db.commit()
    return user


def login(client, email="an@doi.vn", password=PASSWORD):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response


def expire_all_sessions(db, user_id: int) -> None:
    db.execute(text("UPDATE sessions SET expires_at = now() - interval '1 second' WHERE user_id = :id"), {"id": user_id})
    db.commit()
