"""Gemini TTS voices: offered once the Gemini key (the one that makes AI photos) is set, and narration read by it."""

import pytest
from conftest import login, make_user
from fake_services import IMAGE_GEN_KEY
from test_voice import TEN_WORDS, needs_ffmpeg, render, voiced  # noqa: F401  (fixture)
from worker_helpers import committed  # noqa: F401  (fixture)

from reels_api import source_keys, tts, video_options
from reels_api.models import Video
from reels_api.tts import voice_signature

KORE = "gemini:Kore"


@pytest.fixture
def me(db):
    return make_user(db, "gemini-tts@example.com", "Thành viên")


@pytest.fixture
def an(client, me):
    login(client, "gemini-tts@example.com")
    return client


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(tts, "GEMINI_RETRY_SECONDS", 0)


def test_the_gemini_key_that_makes_photos_also_offers_all_thirty_voices(an, fakes):
    payload = an.get("/api/settings/voices").json()
    gemini = [voice for voice in payload["voices"] if voice["service"] == "gemini"]
    assert len(gemini) == 30 and all(voice["id"].startswith("gemini:") for voice in gemini)
    kore = next(voice for voice in gemini if voice["id"] == KORE)
    assert kore == {"id": KORE, "name": "Kore", "description": "Chắc", "preview_url": None, "service": "gemini"}
    assert {voice["service"] for voice in payload["voices"]} == {"elevenlabs", "gemini"}
    assert payload["problems"] == []


def test_without_the_gemini_key_no_gemini_voice_is_offered(an, fakes, monkeypatch):
    monkeypatch.setenv("IMAGE_GEN_API_KEY", "")
    payload = an.get("/api/settings/voices").json()
    assert {voice["service"] for voice in payload["voices"]} == {"elevenlabs"}


def test_with_no_voice_key_at_all_the_voice_list_names_both_pages(an, fakes, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    monkeypatch.setenv("IMAGE_GEN_API_KEY", "")
    refused = an.get("/api/settings/voices")
    assert refused.status_code == 422
    message = refused.json()["message"]
    assert "Nguồn tư liệu" in message and "Mô hình AI" in message and "Gemini" in message


def test_a_gemini_voice_is_a_valid_voice_id_read_with_the_gemini_key():
    assert video_options.clean({"voice_id": KORE})["voice_id"] == KORE
    assert (tts.key_name(KORE), tts.service_name(KORE)) == ("gemini", "Gemini")
    with pytest.raises(video_options.OptionError):
        video_options.clean({"voice_id": "gemini:Ko re"})


def test_the_signature_of_a_gemini_voice_does_not_follow_the_elevenlabs_model(monkeypatch):
    base = voice_signature(TEN_WORDS, KORE)
    monkeypatch.setenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
    assert voice_signature(TEN_WORDS, KORE) == base
    assert voice_signature(TEN_WORDS, "gemini:Puck") != base


def use_kore(factory, video_id):
    with factory() as db:
        db.get(Video, video_id).options = video_options.DEFAULTS | {"voice_id": KORE}
        db.commit()


@needs_ffmpeg
def test_render_reads_a_gemini_voice_as_mp3_and_reuses_it(committed, voiced, fakes):  # noqa: F811
    user, storage, video_id = voiced
    use_kore(committed, video_id)
    with committed() as db:
        source_keys.save(db, "gemini", IMAGE_GEN_KEY, user.id)
        db.commit()
    job = render(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    assert fakes.tts_requests == [] and fakes.vieneu_requests == []
    (request,) = fakes.gemini_tts_requests
    assert request == {"voice": "Kore", "text": TEN_WORDS, "model": "gemini-3.8-flash-tts", "key": IMAGE_GEN_KEY}
    assert render(committed, storage, video_id, user.id).status == "done"
    assert len(fakes.gemini_tts_requests) == 1


@needs_ffmpeg
def test_render_with_a_gemini_voice_and_no_key_says_where_to_paste_one(committed, voiced, fakes, monkeypatch):  # noqa: F811
    user, storage, video_id = voiced
    use_kore(committed, video_id)
    monkeypatch.setenv("IMAGE_GEN_API_KEY", "")
    job = render(committed, storage, video_id, user.id)
    assert job.status == "failed" and "Chưa có key Gemini" in job.error and "Nguồn tư liệu" in job.error
    assert fakes.gemini_tts_requests == []


@needs_ffmpeg
def test_a_per_minute_limit_is_waited_out_and_the_scene_is_read(committed, voiced, fakes):  # noqa: F811
    user, storage, video_id = voiced
    use_kore(committed, video_id)
    fakes.gemini_tts_mode, fakes.gemini_tts_minute_failures = "minute_limit", 2
    job = render(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    assert len(fakes.gemini_tts_requests) == 3


@needs_ffmpeg
def test_the_daily_limit_fails_the_render_at_once_with_a_clear_reason(committed, voiced, fakes):  # noqa: F811
    user, storage, video_id = voiced
    use_kore(committed, video_id)
    fakes.gemini_tts_mode = "daily_limit"
    job = render(committed, storage, video_id, user.id)
    assert job.status == "failed" and "hết lượt đọc lời trong ngày" in job.error
    assert len(fakes.gemini_tts_requests) == 1


def test_a_per_minute_limit_that_does_not_lift_fails_after_the_retries(fakes):
    fakes.gemini_tts_mode, fakes.gemini_tts_minute_failures = "minute_limit", 99
    with pytest.raises(tts.TtsError, match="mỗi phút"):
        tts.synthesize(TEN_WORDS, IMAGE_GEN_KEY, KORE)
    assert len(fakes.gemini_tts_requests) == tts.GEMINI_RETRIES + 1


def test_a_wrong_key_and_a_server_error_are_told_apart(fakes):
    with pytest.raises(tts.TtsError, match="Key Gemini không hợp lệ"):
        tts.synthesize(TEN_WORDS, "wrong-key", KORE)
    fakes.gemini_tts_mode = "error500"
    with pytest.raises(tts.TtsError, match="Gemini đang lỗi"):
        tts.synthesize(TEN_WORDS, IMAGE_GEN_KEY, KORE)
