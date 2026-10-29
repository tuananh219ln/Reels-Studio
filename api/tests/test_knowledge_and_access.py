import pytest
from fastapi.testclient import TestClient

from conftest import login, make_user, make_video
from reels_api.knowledge import default_script_prompt
from reels_api.models import Job


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_knowledge_starts_with_the_defaults(an):
    data = an.get("/api/knowledge").json()
    assert data["script_prompt"] == default_script_prompt() == data["default_script_prompt"]
    assert data["banned_words"] == ["chữa khỏi", "thay thuốc", "diệt tế bào ung thư", "đặc trị", "khắc tinh"]


def test_prompt_and_banned_words_are_saved_and_an_empty_prompt_is_refused(an):
    saved = an.put("/api/knowledge/script-prompt", json={"value": "  Prompt mới [Chủ đề]  "}).json()
    assert saved["script_prompt"] == "Prompt mới [Chủ đề]"
    refused = an.put("/api/knowledge/script-prompt", json={"value": " \n "})
    assert (refused.status_code, refused.json()["message"]) == (422, "Prompt không được để trống")
    assert an.get("/api/knowledge").json()["script_prompt"] == "Prompt mới [Chủ đề]"

    words = an.put("/api/knowledge/banned-words", json={"words": [" thần dược ", "", "thần dược", "đặc trị"]})
    assert words.json()["banned_words"] == ["thần dược", "đặc trị"]

    restored = an.put("/api/knowledge/script-prompt", json={"value": saved["default_script_prompt"]}).json()
    assert restored["script_prompt"] == default_script_prompt()


def test_saved_banned_words_drive_the_warnings(an, db, me, storage):
    video = make_video(db, storage, me, scene_text="Thần dược\nGiàu *canxi*")
    # Candidate titles are only for choosing: neither banned words nor length are checked there.
    video.title_options = ["THẦN DƯỢC " + "RẤT " * 15, "TIÊU ĐỀ 2"]
    db.commit()
    an.put("/api/knowledge/banned-words", json={"words": ["thần dược"]})
    payload = an.get(f"/api/videos/{video.id}").json()
    assert payload["scenes"][0]["warnings"] == ["Có từ cấm: “thần dược”"]
    assert payload["title_scene"]["warnings"] == []
    assert payload["video_warnings"] == []
    assert payload["can_render"] is True


def test_every_file_endpoint_needs_a_login(app, db, me, storage):
    video = make_video(db, storage, me)
    video.mp4_key, video.thumbnail_key = f"videos/{video.id}/v.mp4", f"videos/{video.id}/t.jpg"
    storage.save_bytes(video.mp4_key, b"x")
    storage.save_bytes(video.thumbnail_key, b"x")
    db.commit()
    scene = video.scenes[1].id
    anonymous = TestClient(app)
    for path in (f"/api/videos/{video.id}/video.mp4", f"/api/videos/{video.id}/video.mp4?download=1",
                 f"/api/videos/{video.id}/thumbnail.jpg", f"/api/scenes/{scene}/image",
                 f"/api/scenes/{scene}/preview.jpg", "/api/videos", f"/api/videos/{video.id}", "/api/knowledge"):
        assert anonymous.get(path).status_code == 401, path


def test_changes_need_the_web_origin(app, db, me, storage):
    video = make_video(db, storage, me)
    foreign = TestClient(app, headers={"Origin": "https://evil.example"})
    login_response = foreign.post("/api/auth/login", json={"email": "an@doi.vn", "password": "x"})
    assert login_response.status_code == 403
    for method, path in (("post", "/api/videos"), ("patch", f"/api/videos/{video.id}"),
                         ("delete", f"/api/videos/{video.id}"), ("post", f"/api/videos/{video.id}/render"),
                         ("put", "/api/knowledge/script-prompt")):
        assert getattr(foreign, method)(path).status_code == 403, path


def test_mp4_supports_range_requests_and_download(an, db, me, storage):
    video = make_video(db, storage, me)
    video.mp4_key = f"videos/{video.id}/video-a.mp4"
    storage.save_bytes(video.mp4_key, bytes(range(256)) * 4)
    db.add(Job(video_id=video.id, kind="render", status="done", created_by_id=me.id))
    db.commit()
    partial = an.get(f"/api/videos/{video.id}/video.mp4", headers={"Range": "bytes=10-19"})
    assert partial.status_code == 206 and partial.content == bytes(range(10, 20))
    download = an.get(f"/api/videos/{video.id}/video.mp4?download=1")
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["content-type"] == "video/mp4"
