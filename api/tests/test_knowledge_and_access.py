import pytest
from conftest import first_topic, login, make_user, make_video
from fastapi.testclient import TestClient
from sqlalchemy import text

from reels_api.knowledge import default_clone_prompt, default_script_prompt
from reels_api.models import Job


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_the_first_topic_starts_with_the_defaults(an):
    data = an.get("/api/knowledge").json()
    topic = data["topics"][0]
    assert topic["name"] == "Sức khỏe" and topic["video_count"] == 0
    assert topic["script_prompt"] == default_script_prompt() == data["default_script_prompt"]
    assert topic["clone_prompt"] == default_clone_prompt() == data["default_clone_prompt"]
    assert topic["banned_words"] == ["chữa khỏi", "thay thuốc", "diệt tế bào ung thư", "đặc trị", "khắc tinh"]


def test_a_video_from_the_previous_api_version_still_gets_the_first_topic(db, me):
    # That version does not know the column, so its inserts leave it out.
    topic_id = db.execute(
        text(
            "INSERT INTO videos (topic, has_script, created_by_id) VALUES ('x', false, :user) RETURNING knowledge_topic_id"
        ),
        {"user": me.id},
    ).scalar_one()
    assert topic_id == first_topic(db).id


def test_a_new_topic_starts_empty_and_is_saved_on_its_own(an):
    data = an.post("/api/knowledge/topics", json={"name": "  Làm   đẹp "}).json()
    first, topic = data["topics"]
    assert topic["name"] == "Làm đẹp"
    assert (topic["script_prompt"], topic["clone_prompt"], topic["banned_words"]) == ("", "", [])

    path = f"/api/knowledge/topics/{topic['id']}"
    saved = an.patch(path, json={"script_prompt": "  Prompt mới [Chủ đề]  "}).json()["topics"]
    assert saved[1]["script_prompt"] == "Prompt mới [Chủ đề]" and saved[0] == first
    refused = an.patch(path, json={"script_prompt": " \n "})
    assert (refused.status_code, refused.json()["message"]) == (422, "Prompt không được để trống")
    assert an.patch(path, json={"clone_prompt": ""}).status_code == 422
    words = an.patch(path, json={"banned_words": [" thần dược ", "", "thần dược", "đặc trị"]}).json()["topics"]
    assert words[1]["banned_words"] == ["thần dược", "đặc trị"] and words[0]["banned_words"] == first["banned_words"]
    assert an.patch(path, json={"name": "Da đẹp"}).json()["topics"][1]["name"] == "Da đẹp"


def test_a_topics_photo_hint_is_saved_trimmed_may_be_emptied_and_has_a_limit(an):
    topic = an.get("/api/knowledge").json()["topics"][0]
    assert topic["photo_hint"] == ""
    path = f"/api/knowledge/topics/{topic['id']}"
    saved = an.patch(path, json={"photo_hint": "  cây rau đang mọc trong chậu\r\n "}).json()["topics"][0]
    assert saved["photo_hint"] == "cây rau đang mọc trong chậu"
    assert an.patch(path, json={"photo_hint": ""}).json()["topics"][0]["photo_hint"] == ""
    assert an.patch(path, json={"photo_hint": "x" * 1001}).status_code == 422


def test_topic_names_are_required_and_unique(an):
    assert an.post("/api/knowledge/topics", json={"name": "  "}).json()["message"] == "Hãy nhập tên nhóm chủ đề"
    assert (
        an.post("/api/knowledge/topics", json={"name": "sức KHỎE"}).json()["message"] == "Đã có nhóm chủ đề “sức KHỎE”"
    )
    topic = an.post("/api/knowledge/topics", json={"name": "Gan"}).json()["topics"][1]
    assert an.patch(f"/api/knowledge/topics/{topic['id']}", json={"name": "Sức khỏe"}).status_code == 422
    assert an.patch(f"/api/knowledge/topics/{topic['id']}", json={"name": "GAN"}).status_code == 200
    assert an.patch("/api/knowledge/topics/999999", json={"name": "x"}).status_code == 404


def test_a_topic_with_videos_cannot_be_deleted(an, db, me, storage):
    make_video(db, storage, me)
    data = an.get("/api/knowledge").json()
    assert data["topics"][0]["video_count"] == 1
    refused = an.delete(f"/api/knowledge/topics/{data['topics'][0]['id']}")
    assert (refused.status_code, refused.json()["message"]) == (409, "Nhóm chủ đề còn 1 video nên chưa xoá được")
    empty = an.post("/api/knowledge/topics", json={"name": "Gan"}).json()["topics"][1]
    assert len(an.delete(f"/api/knowledge/topics/{empty['id']}").json()["topics"]) == 1


def test_a_topic_without_a_prompt_cannot_write_or_clone(an, db, me, storage):
    empty = an.post("/api/knowledge/topics", json={"name": "Gan"}).json()["topics"][1]
    refused = an.post("/api/videos", json={"topic": "gan", "knowledge_topic_id": empty["id"]})
    assert (refused.status_code, refused.json()["message"]) == (422, "Nhóm chủ đề “Gan” chưa có prompt viết kịch bản")
    video = make_video(db, storage, me)
    video.knowledge_topic_id = empty["id"]
    db.commit()
    clone = an.post(f"/api/videos/{video.id}/clone", json={"request": "đổi"})
    assert (clone.status_code, clone.json()["message"]) == (422, "Nhóm chủ đề “Gan” chưa có prompt nhân bản")


def test_a_clone_stays_in_the_topic_of_its_source(an, db, me, storage):
    topic = an.post("/api/knowledge/topics", json={"name": "Gan"}).json()["topics"][1]
    an.patch(f"/api/knowledge/topics/{topic['id']}", json={"clone_prompt": "Biến thể"})
    video = make_video(db, storage, me)
    video.knowledge_topic_id = topic["id"]
    db.commit()
    assert an.post(f"/api/videos/{video.id}/clone", json={"request": "đổi"}).json()["knowledge_topic"] == "Gan"


def test_only_the_banned_words_of_the_video_topic_warn(an, db, me, storage):
    video = make_video(db, storage, me, scene_text="Thần dược\nGiàu *canxi*")
    # Candidate titles are only for choosing: neither banned words nor length are checked there.
    video.title_options = ["THẦN DƯỢC " + "RẤT " * 15, "TIÊU ĐỀ 2"]
    db.commit()
    data = an.post("/api/knowledge/topics", json={"name": "Gan"}).json()["topics"]
    an.patch(f"/api/knowledge/topics/{data[1]['id']}", json={"banned_words": ["thần dược"]})
    assert an.get(f"/api/videos/{video.id}").json()["scenes"][0]["warnings"] == []

    an.patch(f"/api/knowledge/topics/{data[0]['id']}", json={"banned_words": ["thần dược"]})
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
    for path in (
        f"/api/videos/{video.id}/video.mp4",
        f"/api/videos/{video.id}/video.mp4?download=1",
        f"/api/videos/{video.id}/thumbnail.jpg",
        f"/api/scenes/{scene}/image",
        f"/api/scenes/{scene}/preview.jpg",
        "/api/videos",
        f"/api/videos/{video.id}",
        "/api/knowledge",
    ):
        assert anonymous.get(path).status_code == 401, path


def test_changes_need_the_web_origin(app, db, me, storage):
    video = make_video(db, storage, me)
    foreign = TestClient(app, headers={"Origin": "https://evil.example"})
    login_response = foreign.post("/api/auth/login", json={"email": "an@doi.vn", "password": "x"})
    assert login_response.status_code == 403
    for method, path in (
        ("post", "/api/videos"),
        ("patch", f"/api/videos/{video.id}"),
        ("delete", f"/api/videos/{video.id}"),
        ("post", f"/api/videos/{video.id}/render"),
        ("patch", "/api/knowledge/topics/1"),
    ):
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
