"""A scene's own narration voice (migration 0091): only that scene is read again, and nothing is paid twice."""

import pytest
from conftest import login, make_user, make_video
from sqlalchemy import select
from test_voice import TEN_WORDS, needs_ffmpeg

from reels_api import video_options
from reels_api.jobs import make_voices
from reels_api.models import Scene
from reels_api.tts import voice_signature
from reels_api.videos import made_voice_seconds, render_signature, split_scenes, spoken


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def _two_voiced(db, storage, me):
    video = make_video(db, storage, me, scene_count=2)
    video.options = video_options.DEFAULTS | {"voice_id": "fake-voice-mai"}
    scenes = db.scalars(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position)
    ).all()
    for scene in scenes:
        scene.voice_text = TEN_WORDS
    db.commit()
    return video, scenes


def _voice_all(db, video, storage):
    title, scenes = split_scenes(db, video)
    make_voices(db, video, [scene for scene in (title, *scenes) if scene is not None], storage)


def test_a_scene_voice_is_saved_shown_and_cleared(an, db, me, storage):
    video, (first, _) = _two_voiced(db, storage, me)
    saved = an.patch(f"/api/scenes/{first.id}", json={"voice_id": "fake-voice-nam"})
    assert saved.status_code == 200, saved.text
    shown = next(scene for scene in saved.json()["scenes"] if scene["id"] == first.id)
    assert shown["voice_id"] == "fake-voice-nam"

    cleared = an.patch(f"/api/scenes/{first.id}", json={"voice_id": ""})
    assert next(scene for scene in cleared.json()["scenes"] if scene["id"] == first.id)["voice_id"] is None

    refused = an.patch(f"/api/scenes/{first.id}", json={"voice_id": "two words"})
    assert refused.status_code == 422 and "Mã giọng đọc không hợp lệ" in refused.json()["message"]


def test_the_scene_voice_falls_back_to_the_videos(db, me, storage):
    video, (first, second) = _two_voiced(db, storage, me)
    first.voice_id = "fake-voice-nam"
    assert video_options.scene_voice(video, first) == "fake-voice-nam"
    assert video_options.scene_voice(video, second) == "fake-voice-mai"


@needs_ffmpeg
def test_changing_one_scenes_voice_reads_only_that_scene_again(db, me, storage, fakes):
    video, (first, second) = _two_voiced(db, storage, me)
    _voice_all(db, video, storage)
    made = len(fakes.tts_requests)
    assert made >= 2 and {request["voice_id"] for request in fakes.tts_requests} == {"fake-voice-mai"}
    kept_key = second.voice_key

    first.voice_id = "fake-voice-nam"
    db.commit()
    assert made_voice_seconds(video, first) is None  # stale: it reads with another voice now
    assert made_voice_seconds(video, second) is not None
    _voice_all(db, video, storage)
    new = fakes.tts_requests[made:]
    assert [(request["voice_id"], request["text"]) for request in new] == [("fake-voice-nam", TEN_WORDS)]
    assert second.voice_key == kept_key
    assert first.voice_signature == voice_signature(spoken(video, first), "fake-voice-nam", 1.0)


@needs_ffmpeg
def test_a_scene_with_its_own_voice_is_not_paid_for_again(db, me, storage, fakes):
    # Every place that signs or checks narration must use the scene's voice, or each render would remake it.
    video, (first, _) = _two_voiced(db, storage, me)
    first.voice_id = "fake-voice-nam"
    db.commit()
    _voice_all(db, video, storage)
    made = len(fakes.tts_requests)
    signature = render_signature(video, *split_scenes(db, video))
    _voice_all(db, video, storage)
    assert len(fakes.tts_requests) == made
    assert made_voice_seconds(video, first) is not None
    assert render_signature(video, *split_scenes(db, video)) == signature


def test_a_video_without_scene_voices_keeps_its_fingerprint(db, me, storage):
    video, (first, _) = _two_voiced(db, storage, me)
    before = render_signature(video, *split_scenes(db, video))
    first.voice_id = "fake-voice-mai"  # the video's own voice, named on the scene: the same narration
    assert render_signature(video, *split_scenes(db, video)) == before
    first.voice_id = None
    assert render_signature(video, *split_scenes(db, video)) == before
