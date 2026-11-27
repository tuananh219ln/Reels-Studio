"""Music claimed on YouTube (docs/decisions/2026-11-26-youtube-claimed-music.md): a flagged track goes into no video by
any way music reaches one, and a claim found in YouTube Studio is noted on the video by hand."""

import pytest
from conftest import first_topic, login, make_user, make_video
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)

from reels_api.models import MusicTrack, Video, VideoEvent

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(2000)
DEFAULTS_URL = "/api/settings/my-video-defaults"
NOTE = "Video 409 – HAAWK Publishing, Audiam (Publishing) – 26/11/2026"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def add_track(an, name="Gentle"):
    form = {"topics": ["chung"], "mood": "piano", "name": name}
    return an.post("/api/music", data=form, files={"file": ("nhac.mp3", MP3, "audio/mpeg")}).json()


def claim(an, track_id, note=NOTE):
    return an.patch(f"/api/music/{track_id}", json={"claimed_on_youtube": True, "claimed_note": note})


def test_a_track_is_flagged_and_unflagged_with_its_note(an, db):
    track = add_track(an)
    assert (track["claimed_on_youtube"], track["claimed_at"], track["claimed_note"]) == (False, None, "")

    flagged = claim(an, track["id"]).json()
    assert flagged["claimed_on_youtube"] is True and flagged["claimed_note"] == NOTE and flagged["claimed_at"]
    assert an.get("/api/music").json()[0]["claimed_on_youtube"] is True
    # Saving the form again keeps the time it was first flagged.
    assert claim(an, track["id"]).json()["claimed_at"] == flagged["claimed_at"]

    cleared = an.patch(f"/api/music/{track['id']}", json={"claimed_on_youtube": False}).json()
    assert (cleared["claimed_on_youtube"], cleared["claimed_at"]) == (False, None)
    assert an.patch(f"/api/music/{track['id']}", json={"claimed_note": "a" * 501}).status_code == 422


def test_a_claimed_track_is_refused_for_every_video_and_the_music_stays(an, db, me, storage):
    video = make_video(db, storage, me)
    track = add_track(an)
    claim(an, track["id"])

    refused = an.post(f"/api/videos/{video.id}/music/from-library", json={"track_id": track["id"]})
    assert refused.status_code == 409 and refused.json()["code"] == "track_claimed"
    assert "“Gentle”" in refused.json()["message"] and "Video 409" in refused.json()["message"]
    assert db.get(Video, video.id).music_key is None

    # Cleared, it can be chosen again.
    an.patch(f"/api/music/{track['id']}", json={"claimed_on_youtube": False})
    assert an.post(f"/api/videos/{video.id}/music/from-library", json={"track_id": track["id"]}).status_code == 200


def test_a_claimed_track_is_never_a_default_and_new_videos_start_silent(an, db, storage):
    track = add_track(an)
    assert an.put(DEFAULTS_URL, json={"values": {"music_track_id": track["id"]}}).status_code == 200

    # Claimed after it was chosen: the settings page says so and new videos start without it.
    claim(an, track["id"])
    assert an.get(DEFAULTS_URL).json()["music_track"]["claimed_on_youtube"] is True
    created = an.post("/api/videos", json={"topic": "tim mạch", "knowledge_topic_id": first_topic(db).id}).json()
    assert created["music"] is None

    refused = an.put(DEFAULTS_URL, json={"values": {"music_track_id": track["id"]}})
    assert refused.status_code == 409 and refused.json()["code"] == "track_claimed"


def test_a_claim_is_noted_on_a_video_and_cleared(an, db, me, storage):
    video = make_video(db, storage, me)
    assert an.get(f"/api/videos/{video.id}").json()["youtube_claim"] == {"active": None, "history": []}

    assert an.post(f"/api/youtube/videos/{video.id}/claim", json={"note": "  "}).status_code == 422
    assert an.post(f"/api/youtube/videos/{video.id}/claim/clear", json={}).status_code == 422

    noted = an.post(f"/api/youtube/videos/{video.id}/claim", json={"note": f" {NOTE} "}).json()["youtube_claim"]
    assert noted["active"]["note"] == NOTE and noted["active"]["by"] == me.name
    assert noted["active"]["channel"] == "web" and not noted["active"]["cleared"]

    cleared = an.post(f"/api/youtube/videos/{video.id}/claim/clear", json={"note": "Đã xóa bài hát trong Studio"})
    claims = cleared.json()["youtube_claim"]
    assert claims["active"] is None
    assert [(row["cleared"], row["note"]) for row in claims["history"]] == [
        (True, "Đã xóa bài hát trong Studio"),
        (False, NOTE),
    ]
    assert an.post("/api/youtube/videos/999999/claim", json={"note": NOTE}).status_code == 404


def test_the_assistant_sees_the_flag_is_refused_and_notes_a_claim(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user)
    track = MusicTrack(
        name="Gentle",
        topics=["chung"],
        mood="piano",
        storage_key="music/gentle.mp3",
        created_by_id=user.id,
        claimed_on_youtube=True,
        claimed_note=NOTE,
    )
    db.add(track)
    db.commit()
    storage.save_bytes(track.storage_key, MP3)

    listed = payload(call(mcp_client, token, "list_edit_options"))["music_tracks"]
    assert [(row["id"], row["claimed_on_youtube"], row["claimed_note"]) for row in listed] == [(track.id, True, NOTE)]

    refused = call(mcp_client, token, "set_audio", video_id=video.id, music_track_id=track.id)
    assert refused["isError"] and "đã bị claim trên YouTube" in refused["content"][0]["text"]

    assert call(mcp_client, token, "note_youtube_claim", video_id=video.id)["isError"]
    noted = payload(call(mcp_client, token, "note_youtube_claim", video_id=video.id, note=NOTE))
    assert noted["youtube_claim"]["note"] == NOTE
    event = db.query(VideoEvent).filter_by(video_id=video.id).one()
    assert (event.type, event.channel, event.actor_user_id) == ("youtube_claim", "muse_chat", user.id)
    cleared = payload(call(mcp_client, token, "note_youtube_claim", video_id=video.id, cleared=True))
    assert cleared["youtube_claim"] is None
