"""No Postgres needed: the database is pointed at a closed port."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from reels_api.db import get_db
from reels_api.main import create_app
from reels_api.sessions import COOKIE_NAME

UNAVAILABLE = {"code": "database_unavailable", "message": "Không kết nối được cơ sở dữ liệu, thử lại sau"}


def test_unreachable_database_answers_503(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")
    dead = create_engine("postgresql+psycopg://x:y@127.0.0.1:1/none", connect_args={"connect_timeout": 2})

    def dead_db():
        with sessionmaker(dead)() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = dead_db
    client = TestClient(app, headers={"Origin": "http://localhost:3000"})

    login = client.post("/api/auth/login", json={"email": "an@doi.vn", "password": "mat-khau-dung-1"})
    client.cookies.set(COOKIE_NAME, "bat-ky")
    me = client.get("/api/me")

    for response in (login, me):
        assert response.status_code == 503
        assert response.json() == UNAVAILABLE
