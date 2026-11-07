"""VieNeu voices: the key on Cài đặt › Mô hình AI, its voices in the picker, and narration read by VieNeu."""

import pytest
from conftest import login, make_user
from fake_services import VIENEU_KEY
from test_voice import TEN_WORDS, needs_ffmpeg, render, voiced  # noqa: F401  (fixture)
from worker_helpers import committed  # noqa: F401  (fixture)

from reels_api import source_keys, tts, video_options
from reels_api.models import Video
from reels_api.tts import voice_signature

LAN = "vieneu:Ngọc Lan"


@pytest.fixture
def me(db):
    return make_user(db, "vieneu@example.com", "Thành viên")


@pytest.fixture
def an(client, me):
    login(client, "vieneu@example.com")
    return client


@pytest.fixture(autouse=True)
def fresh_voice_lists():
    tts._voices_cache.clear()
    yield
    tts._voices_cache.clear()


def test_without_a_vieneu_key_only_elevenlabs_voices_are_offered(an, fakes):
    payload = an.get("/api/settings/voices").json()
    assert {voice["service"] for voice in payload["voices"]} == {"elevenlabs"}
    assert payload["problems"] == []


def test_a_vieneu_key_saved_on_the_ai_page_adds_its_voices_beside_elevenlabs(an, fakes):
    before = an.get("/api/settings/sources").json()["vieneu"]
    assert (before["configured"], before["key"]["origin"]) == (False, None)

    saved = an.put("/api/settings/sources/vieneu/key", json={"api_key": VIENEU_KEY})
    assert saved.status_code == 200 and VIENEU_KEY not in saved.text
    assert (saved.json()["vieneu"]["configured"], saved.json()["vieneu"]["key"]["origin"]) == (True, "saved")

    voices = an.get("/api/settings/voices").json()["voices"]
    vieneu = [voice for voice in voices if voice["service"] == "vieneu"]
    assert sorted(voice["id"] for voice in vieneu) == sorted([LAN, "vieneu:Đăng Quân"])
    lan = next(voice for voice in vieneu if voice["id"] == LAN)
    assert lan["description"] == "Nữ · Bắc · Truyền cảm" and lan["preview_url"] is None
    assert {voice["name"] for voice in voices if voice["service"] == "elevenlabs"} == {"Adam", "Mai"}


def test_vieneu_alone_lists_its_voices_and_says_elevenlabs_has_no_key(an, fakes, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    monkeypatch.setenv("VIENEU_API_KEY", VIENEU_KEY)
    payload = an.get("/api/settings/voices").json()
    assert {voice["service"] for voice in payload["voices"]} == {"vieneu"}
    assert len(payload["problems"]) == 1 and "Chưa có key ElevenLabs" in payload["problems"][0]


def test_with_neither_key_the_voice_list_names_both_pages(an, fakes, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    refused = an.get("/api/settings/voices")
    assert refused.status_code == 422
    assert "Nguồn tư liệu" in refused.json()["message"] and "Mô hình AI" in refused.json()["message"]


def test_a_vieneu_voice_name_with_spaces_is_a_valid_voice_id():
    assert video_options.clean({"voice_id": LAN})["voice_id"] == LAN
    for wrong in ("vieneu:Ngọc  Lan", "vieneu:Ngọc\nLan", "an id", "vieneu:" + "x" * 64):
        with pytest.raises(video_options.OptionError):
            video_options.clean({"voice_id": wrong})


def test_the_signature_of_a_vieneu_voice_does_not_follow_the_elevenlabs_model(monkeypatch):
    base = voice_signature(TEN_WORDS, LAN)
    monkeypatch.setenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
    assert voice_signature(TEN_WORDS, LAN) == base
    assert voice_signature(TEN_WORDS, "vieneu:Đăng Quân") != base


def use_lan(factory, video_id):
    with factory() as db:
        db.get(Video, video_id).options = video_options.DEFAULTS | {"voice_id": LAN}
        db.commit()


@needs_ffmpeg
def test_render_reads_a_vieneu_voice_with_the_vieneu_key_and_reuses_it(committed, voiced, fakes):  # noqa: F811
    user, storage, video_id = voiced
    use_lan(committed, video_id)
    with committed() as db:
        source_keys.save(db, "vieneu", VIENEU_KEY, user.id)
        db.commit()
    job = render(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    assert fakes.tts_requests == []
    (request,) = fakes.vieneu_requests
    assert request == {
        "voice": "Ngọc Lan",
        "input": TEN_WORDS,
        "model": "vieneu-v4",
        "response_format": "mp3",
        "authorization": f"Bearer {VIENEU_KEY}",
    }
    assert render(committed, storage, video_id, user.id).status == "done"
    assert len(fakes.vieneu_requests) == 1


@needs_ffmpeg
def test_render_with_a_vieneu_voice_and_no_key_says_where_to_paste_one(committed, voiced, fakes):  # noqa: F811
    user, storage, video_id = voiced
    use_lan(committed, video_id)
    job = render(committed, storage, video_id, user.id)
    assert job.status == "failed" and "Chưa có key VieNeu" in job.error and "Mô hình AI" in job.error
    assert fakes.vieneu_requests == [] and fakes.tts_requests == []


@needs_ffmpeg
def test_vieneu_trial_limit_fails_the_render_with_a_clear_reason(committed, voiced, fakes, monkeypatch):  # noqa: F811
    user, storage, video_id = voiced
    use_lan(committed, video_id)
    monkeypatch.setenv("VIENEU_API_KEY", VIENEU_KEY)
    fakes.vieneu_mode = "trial_limit"
    job = render(committed, storage, video_id, user.id)
    assert job.status == "failed" and "dùng thử đã hết lượt" in job.error
    assert len(fakes.vieneu_requests) == 1
