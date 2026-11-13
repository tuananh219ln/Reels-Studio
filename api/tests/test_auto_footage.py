"""Automatic footage must select a visible segment, preserve edits and fall back without paid retries."""

import io
import json
import subprocess

import pytest
from conftest import clip_bytes, login, make_user, make_video, needs_ffmpeg
from PIL import Image
from sqlalchemy import select

from reels_api import auto_photos
from reels_api.models import AppSetting, Job, Scene


def test_footage_is_opt_in_and_logs_its_switch(client, db):
    make_user(db)
    login(client)
    assert client.get("/api/settings/sources").json().get("auto_footage") is False
    response = client.put("/api/settings/auto-footage", json={"enabled": True})
    assert response.status_code == 200
    assert response.json()["auto_footage"] is True
    entries = client.get("/api/edit-logs?entity_type=settings_sources&entity_id=1").json()["entries"]
    assert entries[0]["changes"]["auto_footage"] == {"old": False, "new": True}


@needs_ffmpeg
@pytest.mark.parametrize("answer,accepted", [({"index": 1}, True), ({"index": None}, False), ({"index": 999}, False)])
def test_job_selects_and_cuts_footage_or_falls_back_to_photo(
    db, storage, fakes, monkeypatch, tmp_path, answer, accepted
):
    from reels_api import llm, youtube_footage

    user = make_user(db)
    video = make_video(db, storage, user, scene_count=0, images=False)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id))
    scene.seconds = 2
    scene.keywords = ["canh bí đỏ"]
    scene.keywords_en = ["pumpkin soup"]
    db.add(AppSetting(key="auto_footage", value=True))
    job = Job(video_id=video.id, kind="photos", status="running", created_by_id=user.id)
    db.add(job)
    db.commit()
    source = tmp_path / "source.mp4"
    source.write_bytes(clip_bytes(tmp_path, seconds=8, size="576x1024"))
    monkeypatch.setattr(youtube_footage, "search", lambda keyword: ["https://www.youtube.com/watch?v=abcdefghijk"])
    monkeypatch.setattr(youtube_footage, "download", lambda url, folder: source)
    # No stock clips in this case: a rejected YouTube candidate must reach the existing photo search.
    monkeypatch.setattr("reels_api.stock_clips.search", lambda *args: [])
    fakes.claude_replies = [answer]
    complete = llm.complete

    def inspect_frames(target, prompt, label, images):
        assert all(Image.open(io.BytesIO(frame)).size == (360, 640) for frame in images)
        return complete(target, prompt, label, images)

    monkeypatch.setattr(llm, "complete", inspect_frames)

    auto_photos.run(db, job, storage)

    db.refresh(scene)
    assert scene.image_auto
    assert scene.seconds == 2, "selecting footage must not overwrite script timing"
    assert job.claude_calls == 1
    if accepted:
        assert scene.video_key and storage.exists(scene.video_key)
        # Six spoken words plus MP3 padding and lead/tail need 2.5 s, plus 0.4 s of clip spare.
        assert scene.voice_key
        assert scene.video_seconds == pytest.approx(2.9, abs=0.05)
        assert scene.image_key is None and scene.video_sound is False
        assert scene.image_source == "https://www.youtube.com/watch?v=abcdefghijk"
        assert video.thumbnail_key and storage.exists(video.thumbnail_key)
    else:
        assert scene.video_key is None and scene.image_key and storage.exists(scene.image_key)


def test_youtube_search_filters_long_live_and_untrusted_results(monkeypatch):
    from reels_api import youtube_footage

    entries = [
        {"id": "abcdefghijk", "duration": 30},
        {"id": "longlonglon", "duration": 900},
        {"id": "liveliveliv", "duration": 20, "live_status": "is_live"},
        {"id": "https://127.0.0.1/private", "duration": 20},
    ]

    def run(argv, **kwargs):
        assert argv[-1] == "ytsearch10:canh bí đỏ"
        assert kwargs["timeout"] <= 45
        return subprocess.CompletedProcess(argv, 0, json.dumps({"entries": entries}), "")

    monkeypatch.setattr(subprocess, "run", run)
    assert youtube_footage.search("canh bí đỏ") == ["https://www.youtube.com/watch?v=abcdefghijk"]


def test_youtube_search_timeout_is_a_bounded_source_failure(monkeypatch):
    from reels_api import youtube_footage

    def run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(youtube_footage.FootageError, match="YouTube"):
        youtube_footage.search("canh")


@needs_ffmpeg
def test_same_query_uses_another_clip_and_never_replaces_a_manual_pick(db, storage, fakes, monkeypatch, tmp_path):
    from reels_api import youtube_footage

    user = make_user(db)
    video = make_video(db, storage, user, scene_count=2)
    scenes = db.scalars(select(Scene).where(Scene.video_id == video.id).order_by(Scene.position)).all()
    kept = scenes[-1].image_key
    for scene in scenes[:2]:
        scene.image_key, scene.image_source = None, None
        scene.seconds, scene.keywords = 2, ["canh bí đỏ"]
    db.add(AppSetting(key="auto_footage", value=True))
    job = Job(video_id=video.id, kind="photos", status="running", created_by_id=user.id)
    db.add(job)
    db.commit()
    source = tmp_path / "source.mp4"
    source.write_bytes(clip_bytes(tmp_path, seconds=8, size="576x1024"))
    urls = ["https://www.youtube.com/watch?v=abcdefghijk", "https://www.youtube.com/watch?v=bcdefghijkl"]
    monkeypatch.setattr(youtube_footage, "search", lambda keyword: urls)
    monkeypatch.setattr(youtube_footage, "download", lambda url, folder: source)
    monkeypatch.setattr("reels_api.stock_clips.search", lambda *args: [])
    fakes.claude_replies = [{"index": 0}, {"index": 0}]

    auto_photos.run(db, job, storage)

    assert [scene.image_source for scene in scenes[:2]] == urls
    assert all(scene.video_key for scene in scenes[:2])
    assert scenes[-1].image_key == kept and not scenes[-1].image_auto
    assert job.claude_calls == 2


@needs_ffmpeg
def test_single_backdrop_keeps_content_photos_for_insets(db, storage, fakes, monkeypatch, tmp_path):
    from reels_api import youtube_footage

    user = make_user(db)
    video = make_video(db, storage, user, scene_count=1, images=False)
    video.mode = "single"
    db.add(AppSetting(key="auto_footage", value=True))
    job = Job(video_id=video.id, kind="photos", status="running", created_by_id=user.id)
    db.add(job)
    db.commit()
    source = tmp_path / "source.mp4"
    source.write_bytes(clip_bytes(tmp_path, seconds=8, size="576x1024"))
    monkeypatch.setattr(youtube_footage, "search", lambda keyword: ["https://www.youtube.com/watch?v=abcdefghijk"])
    monkeypatch.setattr(youtube_footage, "download", lambda url, folder: source)
    fakes.claude_replies = [{"index": 0}]

    auto_photos.run(db, job, storage)

    scenes = db.scalars(select(Scene).where(Scene.video_id == video.id).order_by(Scene.position)).all()
    assert scenes[0].video_key and scenes[0].image_key is None
    assert scenes[1].image_key and scenes[1].video_key is None
    assert job.claude_calls == 1


def test_no_model_falls_back_without_contacting_video_sources(db, storage, fakes, monkeypatch):
    from reels_api import youtube_footage

    user = make_user(db)
    video = make_video(db, storage, user, scene_count=0, images=False)
    db.add(AppSetting(key="auto_footage", value=True))
    job = Job(video_id=video.id, kind="photos", status="running", created_by_id=user.id)
    db.add(job)
    db.commit()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    def unexpected_search(keyword):
        pytest.fail("A missing vision model must not download candidates it cannot judge")

    monkeypatch.setattr(youtube_footage, "search", unexpected_search)
    auto_photos.run(db, job, storage)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id))
    assert scene.image_key and not scene.video_key
    assert not job.claude_calls


@needs_ffmpeg
def test_unavailable_youtube_uses_stock_video_automatically(db, storage, fakes, monkeypatch):
    from reels_api import youtube_footage

    user = make_user(db)
    video = make_video(db, storage, user, scene_count=0, images=False)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id))
    scene.seconds, scene.keywords_en = 2, ["pumpkin soup"]
    db.add(AppSetting(key="auto_footage", value=True))
    job = Job(video_id=video.id, kind="photos", status="running", created_by_id=user.id)
    db.add(job)
    db.commit()

    def unavailable(keyword):
        raise youtube_footage.FootageError("YouTube đang chặn yêu cầu")

    monkeypatch.setattr(youtube_footage, "search", unavailable)
    fakes.claude_replies = [{"index": 0}]
    auto_photos.run(db, job, storage)
    assert scene.video_key and storage.exists(scene.video_key)
    assert scene.image_source.startswith(fakes.url + "/clips/")
    assert fakes.clip_queries == [("pexels", "pumpkin soup")]
    assert scene.voice_key
    assert scene.video_seconds == pytest.approx(2.9, abs=0.05)
    assert job.claude_calls == 1


@needs_ffmpeg
def test_a_provider_failure_is_not_retried_for_every_scene(db, storage, fakes, monkeypatch, tmp_path):
    from reels_api import crypto, youtube_footage
    from reels_api.models import LlmProvider

    user = make_user(db)
    video = make_video(db, storage, user, scene_count=1, images=False)
    db.add(AppSetting(key="auto_footage", value=True))
    job = Job(video_id=video.id, kind="photos", status="running", created_by_id=user.id)
    db.add(job)
    db.commit()
    source = tmp_path / "source.mp4"
    source.write_bytes(clip_bytes(tmp_path, seconds=8, size="576x1024"))
    monkeypatch.setattr(youtube_footage, "search", lambda keyword: ["https://www.youtube.com/watch?v=abcdefghijk"])
    monkeypatch.setattr(youtube_footage, "download", lambda url, folder: source)
    # The Anthropic fake does not reject keys; the OpenAI fake returns a real HTTP 401 here.
    db.add(AppSetting(key="llm_provider", value="openai"))
    db.add(
        LlmProvider(
            id="openai",
            base_url=fakes.url + "/openai/v1",
            model="fake-model",
            key_encrypted=crypto.encrypt("wrong-fake-key"),
        )
    )
    db.commit()
    auto_photos.run(db, job, storage)
    assert job.claude_calls == 1
    assert all(scene.image_key for scene in db.scalars(select(Scene).where(Scene.video_id == video.id)))


@needs_ffmpeg
def test_automatic_clip_is_cut_after_actual_narration_length_is_known(db, storage, fakes, monkeypatch, tmp_path):
    from reels_api import youtube_footage

    user = make_user(db)
    video = make_video(db, storage, user, scene_count=0, images=False)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id))
    scene.seconds, scene.seconds_auto = 1, True
    scene.voice_text = "Món canh quen thuộc giúp bữa cơm thêm đa dạng."
    db.add(AppSetting(key="auto_footage", value=True))
    job = Job(video_id=video.id, kind="photos", status="running", created_by_id=user.id)
    db.add(job)
    db.commit()
    source = tmp_path / "long-source.mp4"
    source.write_bytes(clip_bytes(tmp_path, seconds=8, size="576x1024"))
    monkeypatch.setattr(youtube_footage, "search", lambda keyword: ["https://www.youtube.com/watch?v=abcdefghijk"])
    monkeypatch.setattr(youtube_footage, "download", lambda url, folder: source)
    fakes.claude_replies = [{"index": 0}]

    auto_photos.run(db, job, storage)

    assert scene.voice_key and scene.voice_seconds > 2.5
    assert scene.seconds > 3
    assert scene.video_seconds >= scene.seconds + 0.39
    assert scene.video_seconds > 3.4, "the old pre-TTS cut was only 1.4 seconds"
