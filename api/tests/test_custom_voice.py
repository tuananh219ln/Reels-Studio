"""An uploaded MP3 as a scene's narration (docs/specs/custom-scene-voice-upload): stored with its length, never read
again by a voice service, part of the render's fingerprint, and removable."""

import subprocess

import pytest
from conftest import login, make_user, make_video
from sqlalchemy import select
from test_voice import TEN_WORDS, needs_ffmpeg
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import routes_videos
from reels_api.models import Scene, Video
from reels_api.storage import DirectoryStorage
from reels_api.tts import voice_signature
from reels_api.videos import (
    CUSTOM_VOICE,
    auto_seconds,
    made_voice_seconds,
    render_signature,
    split_scenes,
)
from reels_render.ffmpeg import probe


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


def tone_mp3(tmp_path, seconds: float, frequency: int = 440) -> bytes:
    """A real MP3 of a tone, as a voice made outside the app would be."""
    path = tmp_path / f"voice-{seconds}-{frequency}.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:duration={seconds}",
            "-c:a",
            "libmp3lame",
            str(path),
        ],
        check=True,
    )
    return path.read_bytes()


def upload(an, scene_id, data, name="giong-chi.mp3"):
    return an.post(f"/api/scenes/{scene_id}/voice", files={"file": (name, data, "audio/mpeg")})


def scene_payload(payload, scene_id) -> dict:
    return next(scene for scene in payload["scenes"] if scene["id"] == scene_id)


# --- Upload and remove ---


@needs_ffmpeg
def test_an_upload_becomes_the_scene_narration_with_its_length(an, db, me, storage, tmp_path):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    scene.voice_text, scene.seconds_auto = "Cá nhỏ giàu canxi", True
    db.commit()
    response = upload(an, scene.id, tone_mp3(tmp_path, 2.5))
    assert response.status_code == 200, response.text
    shown = scene_payload(response.json(), scene.id)
    assert shown["voice_custom"] is True and shown["voice_name"] == "giong-chi.mp3"
    assert shown["voice_seconds"] == pytest.approx(2.5, abs=0.1)
    assert shown["voice_url"] is not None
    # The voice text stays for the captions; the scene follows the file's length.
    assert shown["voice_text"] == "Cá nhỏ giàu canxi"
    db.expire_all()
    scene = db.get(Scene, scene.id)
    assert scene.voice_signature.startswith(CUSTOM_VOICE) and len(scene.voice_signature) == 64
    assert scene.seconds == auto_seconds(scene.voice_seconds)
    assert an.get(f"/api/scenes/{scene.id}/voice.mp3").content == storage.path(scene.voice_key).read_bytes()


@needs_ffmpeg
def test_a_new_upload_replaces_the_file_and_removing_it_brings_the_voice_back(an, db, me, storage, tmp_path):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    scene.voice_text = TEN_WORDS
    db.commit()
    upload(an, scene.id, tone_mp3(tmp_path, 1.0))
    db.expire_all()
    first_key = db.get(Scene, scene.id).voice_key
    upload(an, scene.id, tone_mp3(tmp_path, 2.0), name="lan-2.mp3")
    db.expire_all()
    assert not storage.exists(first_key), "the replaced file is deleted"
    second_key = db.get(Scene, scene.id).voice_key
    removed = an.delete(f"/api/scenes/{scene.id}/voice")
    assert removed.status_code == 200, removed.text
    shown = scene_payload(removed.json(), scene.id)
    assert shown["voice_custom"] is False and shown["voice_name"] is None and shown["voice_url"] is None
    assert not storage.exists(second_key)
    db.expire_all()
    scene = db.get(Scene, scene.id)
    assert scene.voice_key is None and scene.voice_signature is None and scene.voice_seconds is None


def test_a_non_mp3_or_oversized_file_is_refused(an, db, me, storage, monkeypatch):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    fake = upload(an, scene.id, b"RIFF\x00\x00\x00\x00WAVEfmt " + bytes(100), name="giong.mp3")
    assert fake.status_code == 415 and fake.json()["code"] == "invalid_voice"
    monkeypatch.setattr(routes_videos, "MAX_VOICE_BYTES", 1000)
    big = upload(an, scene.id, b"ID3" + bytes(2000))
    assert big.status_code == 413 and "20 MB" in big.json()["message"]


def test_an_mp3_ffprobe_cannot_read_is_refused_and_not_stored(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    response = upload(an, scene.id, b"ID3" + bytes(500))
    assert response.status_code == 415 and "độ dài" in response.json()["message"]
    assert not any(path.name.startswith("voice-") for path in storage.path(f"videos/{video.id}").iterdir())


@needs_ffmpeg
def test_only_the_video_maker_changes_its_voice(client, db, storage, tmp_path):
    maker = make_user(db)
    make_user(db, email="binh@doi.vn", name="Bình")
    video = make_video(db, storage, maker)
    scene = first_scene(db, video)
    login(client, email="binh@doi.vn")
    response = upload(client, scene.id, tone_mp3(tmp_path, 1.0))
    assert response.status_code == 403 and "người tạo" in response.json()["message"]
    assert client.delete(f"/api/scenes/{scene.id}/voice").status_code == 403


@needs_ffmpeg
def test_no_upload_while_a_job_holds_the_video(an, db, me, storage, tmp_path):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    an.patch(f"/api/scenes/{scene.id}", json={"voice_text": TEN_WORDS})
    assert an.post(f"/api/videos/{video.id}/voices").status_code == 200
    response = upload(an, scene.id, tone_mp3(tmp_path, 1.0))
    assert response.status_code == 409 and response.json()["code"] == "video_locked"


# --- Reuse and fingerprint ---


def test_an_uploaded_narration_stands_whatever_the_text_and_voice(db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    scene.voice_text, scene.voice_key, scene.voice_seconds = "một", "videos/x/voice.mp3", 2.0
    scene.voice_signature = "custom:abc"
    assert made_voice_seconds(video, scene) == 2.0
    scene.voice_text, scene.voice_id = "hai", "vieneu:Ngọc Lan"
    assert made_voice_seconds(video, scene) == 2.0
    # A voice service's narration still needs its own text and voice.
    scene.voice_signature = voice_signature("một")
    assert made_voice_seconds(video, scene) is None


def test_another_file_changes_the_fingerprint_and_service_voices_keep_theirs(db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    scene.voice_text = TEN_WORDS
    db.commit()
    title, scenes = split_scenes(db, video)
    service = render_signature(video, title, scenes)
    # A narration made by the service does not change the fingerprint: MP4s rendered before uploads stay current.
    scene.voice_key, scene.voice_seconds, scene.voice_signature = "videos/x/a.mp3", 2.0, voice_signature(TEN_WORDS)
    assert render_signature(video, title, scenes) == service
    scene.voice_signature = "custom:aaaa"
    first = render_signature(video, title, scenes)
    scene.voice_signature = "custom:bbbb"
    assert len({service, first, render_signature(video, title, scenes)}) == 3


@needs_ffmpeg
def test_a_new_upload_marks_the_mp4_outdated(an, db, me, storage, tmp_path):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    scene.voice_text = TEN_WORDS
    db.commit()
    upload(an, scene.id, tone_mp3(tmp_path, 1.0))
    db.expire_all()
    video = db.get(Video, video.id)
    title, scenes = split_scenes(db, video)
    video.mp4_key, video.rendered_signature = "videos/x/out.mp4", render_signature(video, title, scenes)
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is False
    upload(an, scene.id, tone_mp3(tmp_path, 1.0, frequency=660))
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is True


# --- Render, in process ---


@needs_ffmpeg
def test_render_uses_the_upload_and_pays_no_voice_service(committed, tmp_path, fakes):
    from reels_api import jobs
    from reels_api.videos import set_custom_voice

    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user, scene_count=1, seconds=2, title_text="", scene_text="")
        video.options = {**(video.options or {}), "captions": "phrase"}
        scene = first_scene(db, video)
        scene.voice_text, scene.seconds_auto = TEN_WORDS, True
        set_custom_voice(db, storage, video, scene, tone_mp3(tmp_path, 3.0), "giong.mp3")
        db.commit()
        video_id = video.id

    voice_job = add_job(committed, video_id, user.id, kind="voice", status="running")
    jobs.run_job(voice_job, committed, storage)
    assert job_row(committed, voice_job).status == "done"
    render_job = add_job(committed, video_id, user.id, kind="render", status="running")
    jobs.run_job(render_job, committed, storage)
    job = job_row(committed, render_job)
    assert job.status == "done", (job.error, job.error_detail)
    assert fakes.tts_requests == [], "the uploaded file is read, not the voice service"
    with committed() as db:
        video = db.get(Video, video_id)
        scene = first_scene(db, video)
        assert scene.voice_text == TEN_WORDS and scene.voice_signature.startswith(CUSTOM_VOICE)
        seconds = float(probe("ffprobe", storage.path(video.mp4_key))["format"]["duration"])
    # Title 3 s + the scene fitted to 3 s of uploaded narration: 0.2 + 3.0 (+ MP3 padding) + 0.4.
    assert seconds == pytest.approx(6.7, abs=0.1)
