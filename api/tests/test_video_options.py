"""A video's own settings (voice, speed, levels, transitions, text style, captions) and the team's defaults."""

import pytest
from conftest import first_topic, login, make_user, make_video
from test_voice import first_scene, needs_ffmpeg, render, voiced  # noqa: F401  (fixture)
from worker_helpers import committed  # noqa: F401  (fixture)

from reels_api import config, video_options
from reels_api.models import Video
from reels_api.videos import render_signature, split_scenes

DEFAULTS_URL = "/api/settings/video-defaults"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_a_video_from_before_renders_the_original_template(db, me, storage):
    video = make_video(db, storage, me)
    assert video.options is None
    assert video_options.effective(video) == video_options.DEFAULTS
    title, scenes = split_scenes(db, video)
    before = render_signature(video, title, scenes)
    # Saving the defaults explicitly changes nothing about the MP4.
    video.options = dict(video_options.DEFAULTS)
    assert render_signature(video, title, scenes) == before
    video.options = video_options.DEFAULTS | {"transition": "cut"}
    assert render_signature(video, title, scenes) != before


def test_the_team_defaults_apply_to_videos_created_afterwards_only(an, db, me, storage):
    old = make_video(db, storage, me)
    assert an.get(DEFAULTS_URL).json() == video_options.VIDEO_FIELDS | video_options.DEFAULTS
    saved = an.put(
        DEFAULTS_URL, json={"values": {"transition": "slide", "voice_speed": "fast", "music_volume": 15}}
    ).json()
    assert (saved["transition"], saved["voice_speed"], saved["music_volume"]) == ("slide", "fast", 15)

    created = an.post("/api/videos", json={"topic": "tim mạch", "knowledge_topic_id": first_topic(db).id}).json()
    assert created["options"]["transition"] == "slide" and created["options"]["voice_speed"] == "fast"
    assert created["music_volume"] == 15
    assert an.get(f"/api/videos/{old.id}").json()["options"]["transition"] == "fade"


def test_bad_defaults_are_refused(an):
    for values, message in (
        ({"transition": "wipe"}, "Giá trị không hợp lệ"),
        ({"music_volume": 150}, "Âm lượng phải từ 0 đến 100%"),
        ({"colour": "pink"}, "Không có tuỳ chọn"),
        ({"ducking": "yes"}, "“Nhỏ nhạc khi có giọng” chỉ nhận bật hoặc tắt"),
    ):
        refused = an.put(DEFAULTS_URL, json={"values": values})
        assert refused.status_code == 422 and refused.json()["message"].startswith(message), values


def test_a_video_changes_its_own_settings_and_can_take_the_team_defaults_back(an, db, me, storage):
    video = make_video(db, storage, me)
    before = an.get(f"/api/videos/{video.id}").json()["title_scene"]["preview_url"]
    payload = an.patch(f"/api/videos/{video.id}", json={"options": {"captions": "word", "text_style": "dark"}}).json()
    assert (payload["options"]["captions"], payload["options"]["text_style"]) == ("word", "dark")
    # The preview is drawn in the new style, so its address changes.
    assert payload["title_scene"]["preview_url"] != before
    refused = an.patch(f"/api/videos/{video.id}", json={"options": {"voice_volume": 101}})
    assert refused.status_code == 422

    an.put(DEFAULTS_URL, json={"values": {"motion": "pan", "voice_enabled": False}})
    reset = an.patch(f"/api/videos/{video.id}", json={"reset_options": True}).json()
    assert reset["options"]["motion"] == "pan" and reset["options"]["captions"] == "off"
    assert reset["voice_enabled"] is False


def test_a_style_change_redraws_the_thumbnail(an, db, me, storage):
    video = make_video(db, storage, me)
    an.patch(f"/api/scenes/{split_scenes(db, video)[0].id}", json={"text": "TIÊU ĐỀ MỚI"})
    db.refresh(video)
    yellow = video.thumbnail_key
    an.patch(f"/api/videos/{video.id}", json={"options": {"text_style": "red"}})
    db.refresh(video)
    assert video.thumbnail_key and video.thumbnail_key != yellow


def test_a_clone_takes_its_sources_settings(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    an.patch(f"/api/videos/{video.id}", json={"options": {"zoom": "strong"}, "voice_enabled": False})
    draft = an.post(f"/api/videos/{video.id}/clone", json={"request": "đổi sang tim mạch"}).json()
    assert draft["options"]["zoom"] == "strong" and draft["voice_enabled"] is False


def test_the_voice_list_comes_from_elevenlabs(an, fakes):
    payload = an.get("/api/settings/voices").json()
    assert payload["default_id"] == config.DEFAULT_VOICE_ID
    assert [voice["name"] for voice in payload["voices"]] == ["Adam", "Mai"]
    assert payload["voices"][0]["description"] == "male, middle aged, american"


def test_without_an_elevenlabs_key_the_voice_list_says_so(an, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    refused = an.get("/api/settings/voices")
    assert refused.status_code == 422 and "ELEVENLABS_API_KEY" in refused.json()["message"]


@needs_ffmpeg
def test_the_chosen_voice_and_speed_make_the_narration_and_a_change_remakes_it(committed, voiced, fakes):  # noqa: F811
    user, storage, video_id = voiced
    with committed() as db:
        db.get(Video, video_id).options = video_options.DEFAULTS | {
            "voice_id": "fake-voice-mai",
            "voice_speed": "fast",
            "captions": "word",
            "transition": "cut",
            "ducking": True,
        }
        db.commit()
    job = render(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    (request,) = fakes.tts_requests
    assert (request["voice_id"], request["speed"]) == ("fake-voice-mai", 1.1)

    # The same voice and speed: reused. Another speed: made again.
    assert render(committed, storage, video_id, user.id).status == "done"
    assert len(fakes.tts_requests) == 1
    with committed() as db:
        video = db.get(Video, video_id)
        video.options = video_options.effective(video) | {"voice_speed": "normal"}
        db.commit()
    assert render(committed, storage, video_id, user.id).status == "done"
    assert len(fakes.tts_requests) == 2 and "speed" not in fakes.tts_requests[1]
