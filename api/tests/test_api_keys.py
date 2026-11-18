"""Backup narration keys of the team: a narration moves to the next key when one is wrong or out of quota, and the
key's row on Cài đặt says why it failed."""

import pytest
from conftest import login, make_user, make_video
from fake_services import ELEVENLABS_KEY, IMAGE_GEN_KEY, VIENEU_KEY
from test_voice import needs_ffmpeg

from reels_api import jobs, source_keys, tts
from reels_api.models import ApiKey, EditLog

BACKUP = f"{ELEVENLABS_KEY}-backup-1111"
BACKUP_2 = f"{ELEVENLABS_KEY}-backup-2222"
WRONG = "wrong-elevenlabs-key-0000"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(tts, "GEMINI_RETRY_SECONDS", 0)


def add(db, by, key, service="elevenlabs", label=""):
    row = source_keys.add(db, service, label, key, by)
    db.commit()
    return row


def read_keys(fakes) -> list[str]:
    """Which key read each ElevenLabs narration; the default fake key shows as itself."""
    return [request.get("key", ELEVENLABS_KEY) for request in fakes.tts_requests]


def errors(an, service="elevenlabs") -> dict:
    payload = an.get("/api/api-keys").json()["services"][service]
    return {"main": payload["main"], **{row["hint"]: row["error"] for row in payload["keys"]}}


# --- Order and fallback ---


def test_the_order_is_main_then_backups_then_env(db, me, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "env-elevenlabs-key-9999")
    source_keys.save(db, "elevenlabs", "main-elevenlabs-key-0000", me.id)
    add(db, me.id, BACKUP)
    second = add(db, me.id, BACKUP_2)
    chain = source_keys.chain(db, "elevenlabs")
    assert [ref.origin for ref in chain] == ["main", "shared", "shared", "env"]
    assert [ref.hint for ref in chain] == ["0000", "1111", "2222", "9999"]
    # "Lên" moves a backup one place earlier.
    source_keys.move(db, second, -1)
    db.commit()
    assert [ref.hint for ref in source_keys.chain(db, "elevenlabs")][1:3] == ["2222", "1111"]


def test_one_key_alone_is_the_main_or_env_key_as_before(db, fakes):
    assert [(ref.key, ref.origin) for ref in source_keys.chain(db, "elevenlabs")] == [(ELEVENLABS_KEY, "env")]
    assert source_keys.chain(db, "pixabay") == []


def test_a_spent_key_passes_the_scene_to_the_next_one(db, me, storage, fakes):
    fakes.exhausted_keys = {ELEVENLABS_KEY}
    add(db, me.id, BACKUP)
    video = make_video(db, storage, me)
    assert jobs.narrate(db, video, "một hai ba", None, set())
    # ElevenLabs says a spent plan with HTTP 401 "quota_exceeded": that moves on too.
    assert read_keys(fakes) == [ELEVENLABS_KEY, BACKUP]


def test_a_wrong_key_passes_the_scene_to_the_next_one(db, me, storage, fakes, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    source_keys.save(db, "elevenlabs", WRONG, me.id)
    add(db, me.id, BACKUP)
    video = make_video(db, storage, me)
    assert jobs.narrate(db, video, "một hai ba", None, set())
    assert read_keys(fakes) == [WRONG, BACKUP]


def test_with_every_key_failing_the_job_says_it_tried_them_all(db, me, storage, fakes, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    source_keys.save(db, "elevenlabs", WRONG, me.id)
    add(db, me.id, BACKUP)
    fakes.exhausted_keys = {BACKUP}
    video = make_video(db, storage, me)
    with pytest.raises(tts.TtsError) as caught:
        jobs.narrate(db, video, "một hai ba", None, set())
    assert "Đã thử hết 2 key ElevenLabs" in caught.value.message
    assert "quota_exceeded" in caught.value.detail


def test_one_key_alone_fails_with_its_own_reason_as_before(db, me, storage, fakes):
    fakes.exhausted_keys = {ELEVENLABS_KEY}
    video = make_video(db, storage, me)
    with pytest.raises(tts.TtsError) as caught:
        jobs.narrate(db, video, "một hai ba", None, set())
    assert caught.value.message == "Tài khoản ElevenLabs đã hết ký tự (credit), cần nạp thêm"


def test_a_server_error_fails_at_once_without_trying_the_next(db, me, storage, fakes):
    fakes.tts_mode = "error500"
    add(db, me.id, BACKUP)
    video = make_video(db, storage, me)
    with pytest.raises(tts.TtsError, match="ElevenLabs đang lỗi"):
        jobs.narrate(db, video, "một hai ba", None, set())
    assert len(fakes.tts_requests) == 1


def test_a_key_that_failed_in_the_job_is_not_asked_again_for_the_next_scenes(db, me, storage, fakes):
    fakes.exhausted_keys = {ELEVENLABS_KEY}
    add(db, me.id, BACKUP)
    video = make_video(db, storage, me)
    failed: set[str] = set()
    jobs.narrate(db, video, "cảnh một", None, failed)
    jobs.narrate(db, video, "cảnh hai", None, failed)
    assert read_keys(fakes) == [ELEVENLABS_KEY, BACKUP, BACKUP]


def test_a_spent_vieneu_trial_key_moves_on(db, me, storage, fakes):
    source_keys.save(db, "vieneu", VIENEU_KEY, me.id)
    add(db, me.id, f"{VIENEU_KEY}-backup", "vieneu")
    fakes.exhausted_keys = {VIENEU_KEY}
    video = make_video(db, storage, me)
    jobs.narrate(db, video, "một hai ba", "vieneu:Ngọc Lan", set())
    assert [request["authorization"] for request in fakes.vieneu_requests] == [
        f"Bearer {VIENEU_KEY}",
        f"Bearer {VIENEU_KEY}-backup",
    ]


@needs_ffmpeg
def test_a_gemini_key_out_of_the_day_s_requests_moves_to_the_next(db, me, storage, fakes):
    backup = f"{IMAGE_GEN_KEY}-backup"
    add(db, me.id, backup, "gemini")
    fakes.exhausted_keys = {IMAGE_GEN_KEY}
    video = make_video(db, storage, me)
    assert jobs.narrate(db, video, "một hai ba", "gemini:Kore", set())
    assert [request["key"] for request in fakes.gemini_tts_requests] == [IMAGE_GEN_KEY, backup]


def test_a_gemini_per_minute_limit_waits_on_the_same_key(db, me, storage, fakes):
    add(db, me.id, f"{IMAGE_GEN_KEY}-backup", "gemini")
    fakes.gemini_tts_mode, fakes.gemini_tts_minute_failures = "minute_limit", 99
    video = make_video(db, storage, me)
    with pytest.raises(tts.TtsError, match="mỗi phút"):
        jobs.narrate(db, video, "một hai ba", "gemini:Kore", set())
    assert {request["key"] for request in fakes.gemini_tts_requests} == {IMAGE_GEN_KEY}


def test_photos_keep_using_the_main_gemini_key(db, me, fakes):
    add(db, me.id, f"{IMAGE_GEN_KEY}-backup", "gemini")
    assert source_keys.get(db, "gemini") == IMAGE_GEN_KEY


# --- Each key's error, shown on its row ---


def test_the_failing_key_shows_why_until_it_reads_again(an, db, me, storage, fakes, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    source_keys.save(db, "elevenlabs", WRONG, me.id)
    add(db, me.id, BACKUP)
    fakes.exhausted_keys = {BACKUP}
    video = make_video(db, storage, me)
    with pytest.raises(tts.TtsError):
        jobs.narrate(db, video, "một hai ba", None, set())
    shown = errors(an)
    assert shown["main"]["error"].startswith("Key ElevenLabs không hợp lệ hoặc đã bị thu hồi")
    assert shown["main"]["at"]
    assert shown["1111"] == "Tài khoản ElevenLabs đã hết ký tự (credit), cần nạp thêm"
    # The backup has credit again: it reads and its error goes.
    fakes.exhausted_keys = set()
    jobs.narrate(db, video, "một hai ba", None, set())
    db.commit()
    shown = errors(an)
    assert shown["1111"] is None
    assert shown["main"]["error"].startswith("Key ElevenLabs không hợp lệ")
    # A new main key starts clean.
    source_keys.save(db, "elevenlabs", ELEVENLABS_KEY, me.id)
    db.commit()
    assert errors(an)["main"] is None


def test_a_server_error_marks_no_key(an, db, me, storage, fakes):
    fakes.tts_mode = "error500"
    add(db, me.id, BACKUP)
    video = make_video(db, storage, me)
    with pytest.raises(tts.TtsError):
        jobs.narrate(db, video, "một hai ba", None, set())
    assert errors(an) == {"main": None, "1111": None}


# --- The API ---


def test_keys_go_in_and_only_their_name_and_last_characters_come_back(an):
    added = an.post("/api/api-keys", json={"service": "elevenlabs", "api_key": BACKUP, "label": "Key của An"})
    assert added.status_code == 200, added.text
    assert BACKUP not in added.text
    rows = added.json()["services"]["elevenlabs"]["keys"]
    assert [(row["label"], row["hint"], row["readable"], row["error"]) for row in rows] == [
        ("Key của An", "1111", True, None)
    ]
    second = an.post("/api/api-keys", json={"service": "gemini", "api_key": BACKUP_2}).json()
    assert second["services"]["gemini"]["keys"][0]["label"] == "Key dự phòng 1"
    assert BACKUP not in an.get("/api/api-keys").text
    assert an.get("/api/settings/sources").status_code == 200


def test_keys_are_renamed_moved_and_removed(an, db, me):
    first = add(db, me.id, BACKUP)
    second = add(db, me.id, BACKUP_2)
    moved = an.patch(f"/api/api-keys/{second.id}", json={"move": -1, "label": "Dự phòng chính"}).json()
    keys = moved["services"]["elevenlabs"]["keys"]
    assert [row["hint"] for row in keys] == ["2222", "1111"]
    assert keys[0]["label"] == "Dự phòng chính"
    left = an.delete(f"/api/api-keys/{first.id}").json()
    assert [row["hint"] for row in left["services"]["elevenlabs"]["keys"]] == ["2222"]
    assert an.delete(f"/api/api-keys/{first.id}").status_code == 404
    assert db.query(ApiKey).count() == 1


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"service": "elevenlabs", "api_key": "two words"}, "khoảng trắng"),
        ({"service": "elevenlabs", "api_key": ""}, "dán key"),
        ({"service": "elevenlabs", "api_key": BACKUP, "label": "x" * 41}, "40 ký tự"),
    ],
)
def test_a_bad_key_or_label_is_refused(an, body, message):
    refused = an.post("/api/api-keys", json=body)
    assert refused.status_code == 422 and message in refused.json()["message"]


def test_only_narration_services_take_more_keys(an):
    refused = an.post("/api/api-keys", json={"service": "pixabay", "api_key": "abc"})
    assert refused.status_code == 404


def test_a_service_takes_at_most_ten_keys(an, db, me):
    for number in range(source_keys.MAX_KEYS):
        add(db, me.id, f"{BACKUP}-{number}")
    refused = an.post("/api/api-keys", json={"service": "elevenlabs", "api_key": f"{BACKUP}-x"})
    assert refused.status_code == 422 and "Đã đủ 10 key" in refused.json()["message"]


def test_backup_keys_are_logged_by_their_last_characters(an, db):
    an.post("/api/api-keys", json={"service": "elevenlabs", "api_key": BACKUP, "label": "Dự phòng"})
    logged = [entry.changes for entry in db.query(EditLog).order_by(EditLog.id)]
    assert logged == [{"elevenlabs.backup_keys": {"old": None, "new": "Dự phòng …1111"}}]
    assert all(BACKUP not in str(changes) for changes in logged)


def test_the_voice_list_falls_back_to_a_key_that_answers(an, db, me, fakes, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    source_keys.save(db, "elevenlabs", WRONG, me.id)
    add(db, me.id, BACKUP)
    payload = an.get("/api/settings/voices").json()
    assert any(voice["service"] == "elevenlabs" for voice in payload["voices"])
    assert payload["problems"] == []
