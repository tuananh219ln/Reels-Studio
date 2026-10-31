"""Scene narration: voice text editing, ElevenLabs in the render job, lengthened scenes, reuse of made MP3s."""

import shutil

import pytest
from conftest import login, make_user, make_video
from sqlalchemy import select
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import config
from reels_api.models import Job, Scene, Video
from reels_api.storage import DirectoryStorage
from reels_api.tts import voice_signature
from reels_api.videos import render_signature, split_scenes
from reels_render.ffmpeg import probe

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg/ffprobe không có trên PATH")
TEN_WORDS = "một hai ba bốn năm sáu bảy tám chín mười"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def first_scene(db, video) -> Scene:
    return db.scalar(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position).limit(1)
    )


# --- Editing ---


def test_voice_text_and_switch_are_saved(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    payload = an.patch(f"/api/scenes/{scene.id}", json={"voice_text": "  Cá nhỏ giàu canxi \r\n"}).json()
    assert payload["scenes"][0]["voice_text"] == "Cá nhỏ giàu canxi"
    # Nothing made yet: no player, and the scene keeps its seconds.
    assert payload["scenes"][0]["voice_url"] is None and payload["scenes"][0]["fitted_seconds"] == 4
    assert payload["voice_enabled"] is True
    assert an.patch(f"/api/videos/{video.id}", json={"voice_enabled": False}).json()["voice_enabled"] is False
    response = an.patch(f"/api/scenes/{scene.id}", json={"voice_text": "a" * 1001})
    assert response.status_code == 422 and "Lời đọc" in response.json()["message"]


def test_banned_words_in_voice_text_warn(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    payload = an.patch(f"/api/scenes/{scene.id}", json={"voice_text": "Món này chữa khỏi đau lưng"}).json()
    assert "Lời đọc có từ cấm: “chữa khỏi”" in payload["scenes"][0]["warnings"]
    assert payload["can_render"] is True


def test_made_narration_shows_its_length_and_player_until_the_text_changes(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    scene.voice_text, scene.voice_key = "Cá nhỏ giàu canxi", f"videos/{video.id}/voice-{scene.id}-x.mp3"
    scene.voice_signature, scene.voice_seconds = voice_signature("Cá nhỏ giàu canxi"), 5.0
    storage.save_bytes(scene.voice_key, b"mp3")
    db.commit()
    data = an.get(f"/api/videos/{video.id}").json()["scenes"][0]
    assert (data["voice_seconds"], data["fitted_seconds"]) == (5.0, 5.6)
    assert an.get(data["voice_url"]).content == b"mp3"

    data = an.patch(f"/api/scenes/{scene.id}", json={"voice_text": "Cá nhỏ rất giàu canxi"}).json()["scenes"][0]
    assert (data["voice_seconds"], data["voice_url"], data["fitted_seconds"]) == (None, None, 4)


@pytest.mark.parametrize("change", ["voice_text", "voice_off"])
def test_narration_changes_mark_the_mp4_outdated(an, db, me, storage, change):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    scene.voice_text = "Cá nhỏ giàu canxi"
    db.commit()
    title, scenes = split_scenes(db, video)
    video.mp4_key, video.rendered_signature = f"videos/{video.id}/v.mp4", render_signature(video, title, scenes)
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is False
    if change == "voice_text":
        an.patch(f"/api/scenes/{scene.id}", json={"voice_text": "Cá nhỏ ăn cả xương"})
    else:
        an.patch(f"/api/videos/{video.id}", json={"voice_enabled": False})
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is True


def test_videos_without_narration_keep_their_fingerprint(db, me, storage):
    video = make_video(db, storage, me)
    title, scenes = split_scenes(db, video)
    before = render_signature(video, title, scenes)
    video.voice_enabled = False
    assert render_signature(video, title, scenes) == before


def test_deleting_a_scene_deletes_its_narration(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    scene.voice_key = f"videos/{video.id}/voice-{scene.id}-x.mp3"
    storage.save_bytes(scene.voice_key, b"mp3")
    db.commit()
    key = scene.voice_key
    assert an.delete(f"/api/scenes/{scene.id}").status_code == 200
    assert not storage.exists(key)


def test_clone_snapshot_carries_the_voice_text(an, db, me, storage):
    video = make_video(db, storage, me)
    an.patch(f"/api/scenes/{first_scene(db, video).id}", json={"voice_text": "Cá nhỏ ăn cả xương"})
    draft = an.post(f"/api/videos/{video.id}/clone", json={"request": "đổi sang tim mạch"}).json()
    assert (
        "Cảnh 1 (4 giây): Cá nhỏ / Giàu *canxi* — lời đọc: Cá nhỏ ăn cả xương"
        in db.get(Video, draft["id"]).clone_source["script"]
    )


def test_voice_signature_follows_voice_and_model_and_ignores_spacing(monkeypatch):
    base = voice_signature("Cá nhỏ giàu canxi")
    assert voice_signature("  Cá nhỏ \n giàu  canxi ") == base
    monkeypatch.setenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
    assert voice_signature("Cá nhỏ giàu canxi") != base
    monkeypatch.setenv("ELEVENLABS_MODEL", "")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "another-voice")
    assert voice_signature("Cá nhỏ giàu canxi") != base


# --- Render jobs, in process ---


@pytest.fixture
def voiced(committed, tmp_path, fakes):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user, scene_count=1, seconds=2)
        first_scene(db, video).voice_text = TEN_WORDS
        db.commit()
    return user, storage, video.id


def render(factory, storage, video_id, user_id) -> Job:
    from reels_api import jobs

    job_id = add_job(factory, video_id, user_id, kind="render", status="running")
    jobs.run_job(job_id, factory, storage)
    return job_row(factory, job_id)


def mp4_seconds(factory, storage, video_id) -> float:
    with factory() as db:
        return float(probe("ffprobe", storage.path(db.get(Video, video_id).mp4_key))["format"]["duration"])


@needs_ffmpeg
def test_render_reads_adam_lengthens_the_scene_and_reuses_the_narration(committed, voiced, fakes):
    user, storage, video_id = voiced
    job = render(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    assert fakes.tts_requests == [
        {"voice_id": config.DEFAULT_VOICE_ID, "text": TEN_WORDS, "model_id": "eleven_v3", "language_code": "vi"}
    ]
    # Title 3 s + the 2 s scene lengthened to fit 3 s of narration: 0.2 + 3.0 (+ MP3 padding) + 0.4 → 3.7 s.
    assert mp4_seconds(committed, storage, video_id) == pytest.approx(6.7, abs=0.05)
    with committed() as db:
        scene = first_scene(db, db.get(Video, video_id))
        first_key = scene.voice_key
        assert scene.voice_seconds == pytest.approx(3.0, abs=0.1)

    # A re-render pays nothing: the narration made from the same text is reused.
    assert render(committed, storage, video_id, user.id).status == "done"
    assert len(fakes.tts_requests) == 1

    with committed() as db:
        first_scene(db, db.get(Video, video_id)).voice_text = "một hai ba"
        db.commit()
    assert render(committed, storage, video_id, user.id).status == "done"
    assert [request["text"] for request in fakes.tts_requests] == [TEN_WORDS, "một hai ba"]
    assert not storage.exists(first_key)
    # 0.9 s of narration fits in the scene's own 2 s.
    assert mp4_seconds(committed, storage, video_id) == pytest.approx(5.0, abs=0.05)


@needs_ffmpeg
def test_a_new_model_remakes_the_narration_and_marks_the_mp4_outdated(committed, voiced, fakes, monkeypatch):
    user, storage, video_id = voiced
    assert render(committed, storage, video_id, user.id).status == "done"
    monkeypatch.setenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
    with committed() as db:
        video = db.get(Video, video_id)
        title, scenes = split_scenes(db, video)
        assert video.rendered_signature != render_signature(video, title, scenes)
    assert render(committed, storage, video_id, user.id).status == "done"
    assert [request["model_id"] for request in fakes.tts_requests] == ["eleven_v3", "eleven_flash_v2_5"]


@needs_ffmpeg
def test_a_failure_partway_keeps_the_narration_already_paid_for(committed, tmp_path, fakes):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user, scene_count=2, seconds=2)
        _, scenes = split_scenes(db, video)
        scenes[0].voice_text, scenes[1].voice_text = "một hai ba", "bốn năm sáu"
        db.commit()
        video_id = video.id
    fakes.tts_ok_count = 1
    job = render(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "Cảnh 2: Tài khoản ElevenLabs đã hết ký tự (credit), cần nạp thêm")
    with committed() as db:
        _, scenes = split_scenes(db, db.get(Video, video_id))
        assert scenes[0].voice_key and storage.exists(scenes[0].voice_key) and scenes[1].voice_key is None

    fakes.tts_ok_count = None
    assert render(committed, storage, video_id, user.id).status == "done"
    assert [request["text"] for request in fakes.tts_requests] == ["một hai ba", "bốn năm sáu", "bốn năm sáu"]


@needs_ffmpeg
def test_a_scene_with_empty_text_renders(committed, voiced, fakes):
    user, storage, video_id = voiced
    with committed() as db:
        first_scene(db, db.get(Video, video_id)).text = ""
        db.commit()
    job = render(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)


@needs_ffmpeg
def test_narration_switched_off_renders_without_calling_elevenlabs(committed, voiced, fakes):
    user, storage, video_id = voiced
    with committed() as db:
        db.get(Video, video_id).voice_enabled = False
        db.commit()
    assert render(committed, storage, video_id, user.id).status == "done"
    assert fakes.tts_requests == []
    assert mp4_seconds(committed, storage, video_id) == pytest.approx(5.0, abs=0.05)


@needs_ffmpeg
def test_elevenlabs_out_of_credit_fails_the_render_with_a_clear_reason(committed, voiced, fakes):
    user, storage, video_id = voiced
    fakes.tts_mode = "quota"
    job = render(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "Cảnh 1: Tài khoản ElevenLabs đã hết ký tự (credit), cần nạp thêm")
    assert "quota_exceeded" in job.error_detail
    with committed() as db:
        assert db.get(Video, video_id).mp4_key is None


@needs_ffmpeg
def test_narration_pushing_the_total_over_90_seconds_fails_but_keeps_what_was_made(committed, tmp_path, fakes):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    long_text = " ".join(["chữ"] * 40)  # 12 s of fake narration: each of the two scenes becomes 12.7 s
    with committed() as db:
        video = make_video(db, storage, user, scene_count=9, seconds=9)
        _, scenes = split_scenes(db, video)
        for scene in scenes[:2]:
            scene.voice_text = long_text
        db.commit()
        video_id = video.id
    job = render(committed, storage, video_id, user.id)
    assert job.status == "failed"
    assert job.error.startswith("Chưa render được: Tổng độ dài") and "tối đa 90 giây" in job.error
    assert len(fakes.tts_requests) == 2
    with committed() as db:
        _, scenes = split_scenes(db, db.get(Video, video_id))
        assert all(scene.voice_key for scene in scenes[:2]), "a retry must not pay for these again"
