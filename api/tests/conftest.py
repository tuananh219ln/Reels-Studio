from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
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


# --- Videos ---

import io as _io
import sys as _sys

from PIL import Image as _Image

from reels_api.models import KnowledgeTopic, Scene, Video
from reels_api.storage import DirectoryStorage
from reels_render import stock as _stock

_sys.path.insert(0, str(API_DIR / "scripts"))
from fake_services import FakeServices  # noqa: E402

SCENE_TEXT = "Cá nhỏ\nGiàu *canxi*"
TITLE_TEXT = "5 MÓN GIÚP\n*XƯƠNG CHẮC KHỎE*"


@pytest.fixture(autouse=True)
def isolated_files(tmp_path, monkeypatch):
    """Every test gets its own storage folder and Pixabay search cache."""
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setattr(_stock, "default_cache_dir", lambda: tmp_path / "search-cache")
    for name in ("PIXABAY_API_KEY", "PIXABAY_API_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
                 "ELEVENLABS_API_KEY", "ELEVENLABS_API_URL", "ELEVENLABS_VOICE_ID", "ELEVENLABS_MODEL"):
        monkeypatch.setenv(name, "")


@pytest.fixture
def storage(tmp_path) -> DirectoryStorage:
    return DirectoryStorage(tmp_path / "storage")


@pytest.fixture
def fakes(monkeypatch):
    services = FakeServices().start()
    for name, value in services.env().items():
        monkeypatch.setenv(name, value)
    yield services
    services.stop()


def photo_bytes(color=(190, 120, 60), size=(720, 1280), kind="JPEG") -> bytes:
    buffer = _io.BytesIO()
    _Image.new("RGB", size, color).save(buffer, kind)
    return buffer.getvalue()


def first_topic(db) -> KnowledgeTopic:
    """The "Sức khỏe" topic the migration makes, with the default prompts."""
    return db.scalar(select(KnowledgeTopic).order_by(KnowledgeTopic.id))


def make_video(db, storage, user, scene_count=5, seconds=4.0, images=True, topic="xương khớp",
               title_text=TITLE_TEXT, scene_text=SCENE_TEXT) -> Video:
    """A video whose script is saved, like after a finished script job."""
    video = Video(topic=topic, knowledge_topic_id=first_topic(db).id, has_script=True, created_by_id=user.id,
                  title_options=[title_text, "TIÊU ĐỀ 2"],
                  caption="caption", hashtags=["#a"], affiliates=["sữa"], pinned_comment="ghim",
                  self_review=["x"], music_suggestions=["Windy Hill"])
    db.add(video)
    db.flush()
    rows = [Scene(video_id=video.id, is_title=True, position=0, text=title_text, seconds=3, keywords=["canxi"])]
    rows += [Scene(video_id=video.id, is_title=False, position=n, text=scene_text, seconds=seconds,
                   keywords=[f"món {n}"]) for n in range(1, scene_count + 1)]
    db.add_all(rows)
    db.flush()
    if images:
        for index, scene in enumerate(rows):
            key = f"videos/{video.id}/scene-{scene.id}-seed.jpg"
            storage.save_bytes(key, photo_bytes((40 * index % 255, 120, 200 - 20 * index)))
            scene.image_key, scene.image_source = key, f"https://cdn.pixabay.com/seed-{scene.id}.jpg"
    db.commit()
    return video


import shutil as _shutil  # noqa: E402
import subprocess as _subprocess  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(_shutil.which("ffmpeg") is None or _shutil.which("ffprobe") is None,
                                  reason="ffmpeg/ffprobe không có trên PATH")


def clip_bytes(tmp_path, seconds=2.0, size="1280x720", codec="libx264", extension="mp4", rate=25) -> bytes:
    """A test-pattern clip with a tone, as a member's phone clip would have its own sound."""
    path = tmp_path / f"clip-{size}-{seconds}-{codec}.{extension}"
    _subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:v", codec, "-pix_fmt", "yuv420p",
         "-shortest", str(path)],
        check=True,
    )
    return path.read_bytes()
