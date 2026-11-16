"""Google Cloud Text-to-Speech voices: the key on Cài đặt › Mô hình AI, its voices in the picker, and narration read by
Google."""

import pytest
from conftest import login, make_user
from fake_services import GOOGLE_TTS_KEY
from test_voice import TEN_WORDS, needs_ffmpeg, render, voiced  # noqa: F401  (fixture)
from worker_helpers import committed  # noqa: F401  (fixture)

from reels_api import source_keys, tts, video_options
from reels_api.models import Video
from reels_api.tts import voice_signature

ACHERNAR = "google:vi-VN-Chirp3-HD-Achernar"


@pytest.fixture
def me(db):
    return make_user(db, "google-tts@example.com", "Thành viên")


@pytest.fixture
def an(client, me):
    login(client, "google-tts@example.com")
    return client


@pytest.fixture(autouse=True)
def fresh_voice_lists():
    tts._voices_cache.clear()
    yield
    tts._voices_cache.clear()


def test_without_a_google_key_no_google_voice_is_offered(an, fakes):
    payload = an.get("/api/settings/voices").json()
    assert "google" not in {voice["service"] for voice in payload["voices"]}
    assert payload["problems"] == []


def test_a_google_key_saved_on_the_ai_page_adds_its_vietnamese_voices(an, fakes):
    before = an.get("/api/settings/sources").json()["google_tts"]
    assert (before["configured"], before["key"]["origin"]) == (False, None)

    saved = an.put("/api/settings/sources/google_tts/key", json={"api_key": GOOGLE_TTS_KEY})
    assert saved.status_code == 200 and GOOGLE_TTS_KEY not in saved.text
    google = saved.json()["google_tts"]
    assert (google["configured"], google["key"]["origin"], google["key"]["hint"]) == (True, "saved", "0000")

    voices = an.get("/api/settings/voices").json()["voices"]
    offered = {voice["id"]: voice for voice in voices if voice["service"] == "google"}
    assert sorted(offered) == [ACHERNAR, "google:vi-VN-Neural2-D", "google:vi-VN-Standard-A"]
    assert offered[ACHERNAR] == {
        "id": ACHERNAR,
        "name": "Chirp3-HD-Achernar",
        "description": "Nữ · Chirp3-HD",
        "preview_url": None,
        "service": "google",
    }
    assert offered["google:vi-VN-Neural2-D"]["description"] == "Nam · Neural2"
    assert {voice["name"] for voice in voices if voice["service"] == "elevenlabs"} == {"Adam", "Mai"}


def test_a_google_key_change_is_logged_on_the_ai_page_without_the_key(an, fakes):
    assert an.put("/api/settings/sources/google_tts/key", json={"api_key": GOOGLE_TTS_KEY}).status_code == 200
    entries = an.get("/api/edit-logs", params={"entity_type": "settings_ai", "entity_id": 3}).json()["entries"]
    assert [(entry["label"], entry["changes"]) for entry in entries] == [
        ("Giọng đọc Google", {"google_tts.key": {"old": None, "new": "…0000"}})
    ]
    assert GOOGLE_TTS_KEY not in str(entries)


def test_google_alone_lists_its_voices_and_says_elevenlabs_has_no_key(an, fakes, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", GOOGLE_TTS_KEY)
    payload = an.get("/api/settings/voices").json()
    assert {voice["service"] for voice in payload["voices"]} == {"google"}
    assert len(payload["problems"]) == 1 and "Chưa có key ElevenLabs" in payload["problems"][0]


def test_a_wrong_google_key_still_shows_the_other_voices_with_the_reason(an, fakes, monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", "AIzaWrongKey-wrong-wrong")
    payload = an.get("/api/settings/voices").json()
    assert {voice["service"] for voice in payload["voices"]} == {"elevenlabs"}
    assert payload["problems"] == ["Key Google Cloud không hợp lệ: kiểm tra lại ở Cài đặt › Mô hình AI"]


def test_with_no_voice_key_at_all_the_voice_list_names_both_pages(an, fakes, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    refused = an.get("/api/settings/voices")
    assert refused.status_code == 422
    message = refused.json()["message"]
    assert "Nguồn tư liệu" in message and "Mô hình AI" in message and "Google" in message


def test_a_google_voice_name_is_a_valid_voice_id_and_reads_with_the_google_key():
    assert video_options.clean({"voice_id": ACHERNAR})["voice_id"] == ACHERNAR
    assert (tts.key_name(ACHERNAR), tts.service_name(ACHERNAR)) == ("google_tts", "Google")
    with pytest.raises(video_options.OptionError):
        video_options.clean({"voice_id": "google:vi VN"})


def test_the_signature_of_a_google_voice_does_not_follow_the_elevenlabs_model(monkeypatch):
    base = voice_signature(TEN_WORDS, ACHERNAR)
    monkeypatch.setenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
    assert voice_signature(TEN_WORDS, ACHERNAR) == base
    assert voice_signature(TEN_WORDS, "google:vi-VN-Neural2-D") != base


def test_a_text_too_long_for_google_fails_before_calling_it(fakes):
    with pytest.raises(tts.TtsError, match="quá dài"):
        tts.synthesize("chữ " * 2000, GOOGLE_TTS_KEY, ACHERNAR)
    assert fakes.google_tts_requests == []


def use_achernar(factory, video_id):
    with factory() as db:
        db.get(Video, video_id).options = video_options.DEFAULTS | {"voice_id": ACHERNAR}
        db.commit()


@needs_ffmpeg
def test_render_reads_a_google_voice_with_the_google_key_and_reuses_it(committed, voiced, fakes):  # noqa: F811
    user, storage, video_id = voiced
    use_achernar(committed, video_id)
    with committed() as db:
        source_keys.save(db, "google_tts", GOOGLE_TTS_KEY, user.id)
        db.commit()
    job = render(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    assert fakes.tts_requests == [] and fakes.vieneu_requests == []
    (request,) = fakes.google_tts_requests
    assert request == {
        "input": {"text": TEN_WORDS},
        "voice": {"languageCode": "vi-VN", "name": "vi-VN-Chirp3-HD-Achernar"},
        "audioConfig": {"audioEncoding": "MP3"},
        "key": GOOGLE_TTS_KEY,
    }
    assert render(committed, storage, video_id, user.id).status == "done"
    assert len(fakes.google_tts_requests) == 1


@needs_ffmpeg
def test_render_with_a_google_voice_and_no_key_says_where_to_paste_one(committed, voiced, fakes):  # noqa: F811
    user, storage, video_id = voiced
    use_achernar(committed, video_id)
    job = render(committed, storage, video_id, user.id)
    assert job.status == "failed" and "Chưa có key Google" in job.error and "Mô hình AI" in job.error
    assert fakes.google_tts_requests == [] and fakes.tts_requests == []


@needs_ffmpeg
def test_google_billing_off_fails_the_render_with_a_clear_reason(committed, voiced, fakes, monkeypatch):  # noqa: F811
    user, storage, video_id = voiced
    use_achernar(committed, video_id)
    monkeypatch.setenv("GOOGLE_TTS_API_KEY", GOOGLE_TTS_KEY)
    fakes.google_tts_mode = "billing"
    job = render(committed, storage, video_id, user.id)
    assert job.status == "failed" and "chưa bật thanh toán" in job.error
    assert len(fakes.google_tts_requests) == 1
