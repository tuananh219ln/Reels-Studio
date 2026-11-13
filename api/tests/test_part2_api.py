"""Part 2: Pixabay picker, MP3 and volume, "Nhân bản", the job log and the clone prompt."""

import hashlib
import json
import time
from datetime import timedelta

import pytest
from conftest import login, make_user, make_video
from fastapi.testclient import TestClient
from sqlalchemy import select

from reels_api.models import Job, Scene, Video
from reels_api.sessions import now
from reels_api.videos import split_scenes

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(2000)


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def first_scene(db, video) -> int:
    return db.scalar(
        select(Scene.id).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position).limit(1)
    )


def add_mp3(an, video, data=MP3, name="Windy Hill.mp3"):
    return an.post(f"/api/videos/{video.id}/music", files={"file": (name, data, "audio/mpeg")})


# --- "Chọn từ Pixabay" ---


def test_picker_lists_pixabay_results_with_thumbnails(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    fakes.pixabay_results["cá cơm"] = ["a", "b", "c"]
    result = an.get(f"/api/scenes/{first_scene(db, video)}/pixabay", params={"q": "  cá   cơm "}).json()
    assert result["keyword"] == "cá cơm"
    assert result["hits"] == [{"url": fakes.image_url(name), "preview": fakes.image_url(name)} for name in "abc"]
    assert fakes.image_downloads == [], "showing the grid downloads nothing"


def test_choosing_a_result_stores_the_photo_in_the_app(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    fakes.pixabay_results["cá cơm"] = ["a", "b"]
    an.get(f"/api/scenes/{scene}/pixabay", params={"q": "cá cơm"})
    saved = an.post(f"/api/scenes/{scene}/pixabay", json={"keyword": "cá cơm", "url": fakes.image_url("b")})
    assert saved.status_code == 200
    key, source = db.execute(select(Scene.image_key, Scene.image_source).where(Scene.id == scene)).one()
    assert source == fakes.image_url("b") and storage.exists(key) and key.startswith(f"videos/{video.id}/")
    assert saved.json()["scenes"][0]["image_url"].startswith(f"/api/scenes/{scene}/image")


def test_only_an_address_pixabay_returned_can_be_chosen(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    before = db.scalar(select(Scene.image_key).where(Scene.id == scene))
    fakes.pixabay_results["cá cơm"] = ["a"]
    for url in (fakes.image_url("not-a-result"), "http://169.254.169.254/latest/meta-data", "file:///etc/passwd"):
        response = an.post(f"/api/scenes/{scene}/pixabay", json={"keyword": "cá cơm", "url": url})
        assert response.status_code == 422, url
    assert fakes.image_downloads == []
    assert db.scalar(select(Scene.image_key).where(Scene.id == scene)) == before


def test_picker_reports_pixabay_problems_at_the_scene(an, db, me, storage, fakes, monkeypatch):
    from reels_api import routes_videos

    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    assert an.get(f"/api/scenes/{scene}/pixabay", params={"q": " "}).status_code == 422
    monkeypatch.setenv("PIXABAY_API_KEY", "wrong")
    bad_key = an.get(f"/api/scenes/{scene}/pixabay", params={"q": "cá"})
    assert bad_key.status_code == 502 and "Key Pixabay không hợp lệ" in bad_key.json()["message"]
    monkeypatch.setenv("PIXABAY_API_KEY", fakes.env()["PIXABAY_API_KEY"])
    monkeypatch.setattr(routes_videos, "FIND_IMAGE_SECONDS", 1.5)
    fakes.pixabay_mode = "hang"
    started = time.monotonic()
    slow = an.get(f"/api/scenes/{scene}/pixabay", params={"q": "tôm"})
    assert slow.status_code == 502 and "không phản hồi kịp" in slow.json()["message"]
    assert time.monotonic() - started < 5


# --- Music ---


def test_mp3_upload_replace_and_remove(an, db, me, storage):
    video = make_video(db, storage, me)
    first = add_mp3(an, video).json()
    assert first["music"]["name"] == "Windy Hill.mp3" and first["music_volume"] == 25
    assert an.get(first["music"]["url"]).content == MP3
    replaced = add_mp3(an, video, b"\xff\xfb\x90\x64" + bytes(500), name="khac.mp3").json()
    assert replaced["music"]["name"] == "khac.mp3"
    assert [p.name.startswith("music-") for p in storage.path(f"videos/{video.id}").iterdir()].count(True) == 1
    removed = an.delete(f"/api/videos/{video.id}/music").json()
    assert removed["music"] is None
    assert not any(p.name.startswith("music-") for p in storage.path(f"videos/{video.id}").iterdir())


def test_fake_or_oversized_mp3_is_refused(an, db, me, storage, monkeypatch):
    from reels_api import routes_videos

    video = make_video(db, storage, me)
    fake = add_mp3(an, video, b"RIFF\x00\x00\x00\x00WAVEfmt " + bytes(100), name="bai-hat.mp3")
    assert fake.status_code == 415 and "MP3 thật" in fake.json()["message"]
    monkeypatch.setattr(routes_videos, "MAX_MUSIC_BYTES", 1000)
    big = add_mp3(an, video)
    assert (big.status_code, big.json()["message"]) == (413, "File nhạc quá 20 MB, hãy chọn file nhỏ hơn")
    assert db.get(Video, video.id).music_key is None


def test_volume_is_saved_per_video_between_0_and_100(an, db, me, storage):
    video, other = make_video(db, storage, me), make_video(db, storage, me)
    for volume in (0, 100, 60):
        assert an.patch(f"/api/videos/{video.id}", json={"music_volume": volume}).json()["music_volume"] == volume
    assert an.patch(f"/api/videos/{video.id}", json={"music_volume": 101}).status_code == 422
    assert an.patch(f"/api/videos/{video.id}", json={"music_volume": -1}).status_code == 422
    assert an.get(f"/api/videos/{other.id}").json()["music_volume"] == 25


@pytest.mark.parametrize("change", ["add", "replace", "remove", "volume"])
def test_music_changes_mark_the_mp4_outdated(an, db, me, storage, change):
    from reels_api.videos import render_signature, split_scenes

    video = make_video(db, storage, me)
    if change != "add":
        add_mp3(an, video)
        db.refresh(video)
    title, scenes = split_scenes(db, video)
    video.mp4_key, video.rendered_signature = f"videos/{video.id}/v.mp4", render_signature(video, title, scenes)
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is False
    if change in ("add", "replace"):
        add_mp3(an, video)
    elif change == "remove":
        an.delete(f"/api/videos/{video.id}/music")
    else:
        an.patch(f"/api/videos/{video.id}", json={"music_volume": 50})
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is True


# --- "Nhân bản" ---


def test_clone_needs_a_change_request(an, db, me, storage):
    video = make_video(db, storage, me)
    response = an.post(f"/api/videos/{video.id}/clone", json={"request": "   "})
    assert response.status_code == 422 and "yêu cầu đổi" in response.json()["message"]
    assert db.scalars(select(Video)).all() == [video]


def test_clone_snapshots_the_edited_source_and_copies_its_music(an, db, me, storage):
    video = make_video(db, storage, me)
    an.patch(f"/api/scenes/{first_scene(db, video)}", json={"text": "Cá nhỏ đã sửa\nGiàu *canxi*"})
    add_mp3(an, video)
    an.patch(f"/api/videos/{video.id}", json={"music_volume": 40})

    draft = an.post(f"/api/videos/{video.id}/clone", json={"request": "đổi sang mốc 45 tuổi, tim mạch"})
    assert draft.status_code == 201
    payload = draft.json()
    assert payload["id"] != video.id and payload["active_job"]["kind"] == "clone"
    assert payload["topic"] == "đổi sang mốc 45 tuổi, tim mạch" and payload["music_volume"] == 40
    assert payload["clone_of"] == {"title": "5 MÓN GIÚP XƯƠNG CHẮC KHỎE", "request": "đổi sang mốc 45 tuổi, tim mạch"}
    clone = db.get(Video, payload["id"])
    assert "Cảnh 1 (4 giây): Cá nhỏ đã sửa / Giàu *canxi*" in clone.clone_source["script"]
    assert clone.clone_source["topic"] == "xương khớp"
    assert clone.music_key != video.music_key and clone.music_key.startswith(f"videos/{clone.id}/")
    assert storage.path(clone.music_key).read_bytes() == MP3
    # Copied, not moved: the source keeps its own music and volume.
    db.refresh(video)
    assert (video.music_volume, storage.path(video.music_key).read_bytes()) == (40, MP3)
    assert an.get(f"/api/videos/{video.id}").json()["locked"] is False

    # The source stays editable, and deleting it keeps the draft's music.
    assert an.patch(f"/api/videos/{video.id}", json={"caption": "sửa tiếp"}).status_code == 200
    assert an.delete(f"/api/videos/{video.id}").status_code == 200
    assert storage.path(clone.music_key).read_bytes() == MP3
    assert an.get(f"/api/videos/{clone.id}/music.mp3").content == MP3


def test_a_cancelled_clone_draft_reruns_the_clone_with_its_snapshot(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp3(an, video)
    draft = an.post(f"/api/videos/{video.id}/clone", json={"request": "tim mạch"}).json()
    cancelled = an.post(f"/api/jobs/{draft['active_job']['id']}/cancel").json()
    assert cancelled["status"] == "draft" and cancelled["music"] is not None
    again = an.post(f"/api/videos/{draft['id']}/script").json()
    assert again["active_job"]["kind"] == "clone"
    assert db.get(Video, draft["id"]).clone_source["request"] == "tim mạch"


# --- Job log and clone prompt ---


def test_job_log_lists_every_job_with_its_details(an, db, me, storage):
    video = make_video(db, storage, me)
    db.add_all(
        [
            Job(
                video_id=video.id,
                kind="script",
                status="failed",
                created_by_id=me.id,
                claude_calls=2,
                error="Claude trả kịch bản không đúng định dạng",
            ),
            Job(video_id=video.id, kind="render", status="cancelled", created_by_id=me.id),
        ]
    )
    db.commit()
    done = Job(
        video_id=video.id,
        kind="render",
        status="done",
        created_by_id=me.id,
        started_at=now() - timedelta(seconds=30),
        finished_at=now(),
    )
    db.add(done)
    db.commit()
    rows = an.get("/api/jobs").json()
    assert [(row["kind_label"], row["status"]) for row in rows] == [
        ("Render", "done"),
        ("Render", "cancelled"),
        ("Viết kịch bản", "failed"),
    ]
    assert rows[0]["video_title"] == "5 MÓN GIÚP XƯƠNG CHẮC KHỎE" and rows[0]["video_id"] == video.id
    assert rows[0]["duration_seconds"] == pytest.approx(30, abs=1) and rows[0]["created_by"] == "Nguyễn Văn An"
    assert (rows[2]["claude_calls"], rows[2]["error"]) == (2, "Claude trả kịch bản không đúng định dạng")
    assert TestClient(an.app).get("/api/jobs").status_code == 401


def test_job_log_row_tells_the_wait_and_the_job_it_retries(an, db, me, storage):
    video = make_video(db, storage, me)
    first = Job(video_id=video.id, kind="render", status="failed", created_by_id=me.id)
    db.add(first)
    db.commit()
    started = now()
    retry = Job(
        video_id=video.id,
        kind="render",
        status="done",
        created_by_id=me.id,
        retry_of_id=first.id,
        created_at=started - timedelta(seconds=7),
        started_at=started,
        finished_at=started + timedelta(seconds=3),
    )
    db.add(retry)
    db.commit()
    rows = {row["id"]: row for row in an.get("/api/jobs").json()}
    assert rows[retry.id]["retry_of_id"] == first.id
    assert rows[retry.id]["waited_seconds"] == pytest.approx(7, abs=1)
    assert rows[first.id]["retry_of_id"] is None and rows[first.id]["waited_seconds"] is None
    assert "thumbnail_url" in rows[retry.id]


def test_music_file_needs_a_login(app, db, me, storage):
    video = make_video(db, storage, me)
    video.music_key = f"videos/{video.id}/music-a.mp3"
    storage.save_bytes(video.music_key, MP3)
    db.commit()
    assert TestClient(app).get(f"/api/videos/{video.id}/music.mp3").status_code == 401


def test_mp4s_rendered_before_music_existed_are_not_flagged_outdated(an, db, me, storage):
    """The fingerprint format part 1 stored: sha256 of the scene list alone."""
    video = make_video(db, storage, me)
    video.voice_enabled = False  # with narration on the on-screen text is read, which joins the fingerprint
    title, scenes = split_scenes(db, video)
    parts = [[scene.text, scene.seconds, scene.image_key] for scene in [title, *scenes]]
    video.mp4_key = f"videos/{video.id}/v.mp4"
    video.rendered_signature = hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is False
    add_mp3(an, video)
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is True


def test_job_log_pages_back_through_every_job(an, db, me, storage, monkeypatch):
    from reels_api import routes_videos

    monkeypatch.setattr(routes_videos, "JOB_LIST_LIMIT", 2)
    video = make_video(db, storage, me)
    db.add_all([Job(video_id=video.id, kind="render", status="cancelled", created_by_id=me.id) for _ in range(5)])
    db.commit()
    seen, before = [], None
    # Bounded: a paging bug that repeats a page must fail here, not loop forever.
    for _ in range(10):
        page = an.get("/api/jobs", params={} if before is None else {"before": before}).json()
        if not page:
            break
        seen += [row["id"] for row in page]
        before = page[-1]["id"]
    all_ids = db.scalars(select(Job.id).order_by(Job.id.desc())).all()
    assert seen == all_ids and len(seen) == 5


def test_an_mp3_of_exactly_20_mb_is_accepted_and_one_byte_more_is_refused(an, db, me, storage):
    video = make_video(db, storage, me)
    limit = 20 * 1024 * 1024
    head = b"ID3\x04\x00\x00\x00\x00\x00\x00"
    assert add_mp3(an, video, head + bytes(limit - len(head))).status_code == 200
    too_big = add_mp3(an, video, head + bytes(limit - len(head) + 1))
    assert too_big.status_code == 413
    assert storage.path(db.get(Video, video.id).music_key).stat().st_size == limit


@pytest.mark.parametrize("problem", ["bad_key", "hang", "not_an_image"])
def test_choosing_a_grid_photo_reports_pixabay_problems_and_keeps_the_old_photo(
    an, db, me, storage, fakes, monkeypatch, problem
):
    from reels_api import pixabay, routes_videos

    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    before = db.scalar(select(Scene.image_key).where(Scene.id == scene))
    fakes.pixabay_results["cá"] = ["a"]
    an.get(f"/api/scenes/{scene}/pixabay", params={"q": "cá"})
    if problem == "bad_key":
        # A new key means a fresh search, which Pixabay refuses.
        monkeypatch.setattr(pixabay.HitCache, "get", lambda self, keyword: None)
        monkeypatch.setenv("PIXABAY_API_KEY", "wrong")
    elif problem == "hang":
        monkeypatch.setattr(pixabay.HitCache, "get", lambda self, keyword: None)
        monkeypatch.setattr(routes_videos, "FIND_IMAGE_SECONDS", 1.5)
        fakes.pixabay_mode = "hang"
    else:
        monkeypatch.setattr(pixabay.Pixabay, "download", lambda self, url, deadline: None)
    started = time.monotonic()
    response = an.post(f"/api/scenes/{scene}/pixabay", json={"keyword": "cá", "url": fakes.image_url("a")})
    expected = {
        "bad_key": (502, "Key Pixabay không hợp lệ"),
        "hang": (502, "không phản hồi kịp"),
        "not_an_image": (422, "Ảnh này không tải được"),
    }[problem]
    assert response.status_code == expected[0] and expected[1] in response.json()["message"]
    assert time.monotonic() - started < 5
    assert db.scalar(select(Scene.image_key).where(Scene.id == scene)) == before
