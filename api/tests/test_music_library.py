"""The team music library: tracks tagged by topic and mood, and choosing one for a video."""

import pytest

from conftest import client_for, login, make_user, make_video
from reels_api import routes_music
from reels_api.models import MusicTrack, Video

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(2000)
OTHER_MP3 = b"\xff\xfb\x90\x64" + bytes(500)


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def add_track(an, data=MP3, filename="Windy Hill.mp3", topics=("xương khớp",), mood="piano", **fields):
    form = {"topics": list(topics), "mood": mood, **fields}
    return an.post("/api/music", data=form, files={"file": (filename, data, "audio/mpeg")})


def test_upload_lists_and_plays_a_track(an, db, me, storage):
    added = add_track(an, topics=["xương khớp", "tim mạch", "xương khớp"], license_note="Pixabay Music, miễn phí").json()
    assert added["name"] == "Windy Hill"
    # Stored in the fixed order of the list, whatever order the form sent.
    assert added["topics"] == ["tim mạch", "xương khớp"] and added["mood"] == "piano"
    assert added["license_note"] == "Pixabay Music, miễn phí" and added["created_by"] == me.name
    assert an.get(added["url"]).content == MP3
    assert [track["id"] for track in an.get("/api/music").json()] == [added["id"]]
    assert an.get("/api/music/options").json() == {"topics": routes_music.TOPICS, "moods": routes_music.MOODS}


def test_a_given_name_wins_over_the_file_name(an):
    assert add_track(an, name="  Nhạc sáng  ").json()["name"] == "Nhạc sáng"


def test_list_filters_by_topic_mood_and_name(an):
    heart = add_track(an, filename="Tim vui.mp3", topics=["tim mạch"], mood="vui tươi").json()
    bones = add_track(an, filename="Xương piano.mp3", topics=["xương khớp", "chung"], mood="piano").json()
    percent = add_track(an, filename="100% thư giãn.mp3", topics=["giấc ngủ"], mood="thư giãn").json()
    underscore = add_track(an, filename="gan_khoe.mp3", topics=["gan"], mood="nhẹ nhàng").json()

    def ids(query: str) -> list[int]:
        return [track["id"] for track in an.get(f"/api/music{query}").json()]

    assert ids("") == [underscore["id"], percent["id"], bones["id"], heart["id"]]
    assert ids("?topic=xương khớp") == [bones["id"]]
    assert ids("?mood=vui tươi") == [heart["id"]]
    assert ids("?q=PIANO") == [bones["id"]]
    assert ids("?topic=chung&mood=vui tươi") == []
    # LIKE wildcards in the search are plain characters.
    assert ids("?q=%25") == [percent["id"]]
    assert ids("?q=_") == [underscore["id"]]


@pytest.mark.parametrize("topics, mood, message", [
    ([], "piano", "ít nhất một chủ đề"),
    (["ẩm thực"], "piano", "Chủ đề không có"),
    (["gan"], "", "Mood không có"),
    (["gan"], "rock", "Mood không có"),
])
def test_topics_and_mood_must_come_from_the_fixed_lists(an, db, storage, topics, mood, message):
    response = add_track(an, topics=topics, mood=mood)
    assert response.status_code == 422 and message in response.json()["message"]
    assert db.query(MusicTrack).count() == 0
    assert not storage.path("music").exists()


def test_fake_or_oversized_track_is_refused(an, db, storage, monkeypatch):
    fake = add_track(an, data=b"RIFF\x00\x00\x00\x00WAVEfmt " + bytes(100))
    assert fake.status_code == 415 and "MP3 thật" in fake.json()["message"]
    monkeypatch.setattr(routes_music, "MAX_MUSIC_BYTES", 1000)
    assert add_track(an).status_code == 413
    assert db.query(MusicTrack).count() == 0
    assert not storage.path("music").exists()


def test_edit_name_topics_mood_and_license(an):
    track = add_track(an).json()
    edited = an.patch(f"/api/music/{track['id']}", json={
        "name": "Bài mới", "topics": ["gan"], "mood": "trầm lắng", "license_note": "Mua bản quyền 2026",
    }).json()
    assert (edited["name"], edited["topics"], edited["mood"], edited["license_note"]) == (
        "Bài mới", ["gan"], "trầm lắng", "Mua bản quyền 2026")
    assert an.patch(f"/api/music/{track['id']}", json={"topics": []}).status_code == 422
    assert an.patch(f"/api/music/{track['id']}", json={"name": " "}).status_code == 422
    assert an.patch(f"/api/music/{track['id']}", json={"topics": ["ẩm thực"]}).status_code == 422
    assert an.patch(f"/api/music/{track['id']}", json={"mood": "rock"}).status_code == 422
    assert an.patch(f"/api/music/{track['id']}", json={"name": "a" * 201}).status_code == 422
    assert an.patch(f"/api/music/{track['id']}", json={"license_note": "a" * 501}).status_code == 422
    assert an.get("/api/music").json()[0]["mood"] == "trầm lắng"
    assert an.patch("/api/music/999999", json={"name": "x"}).status_code == 404


def test_choosing_a_track_copies_it_into_the_video(an, db, me, storage):
    video = make_video(db, storage, me)
    track = add_track(an, filename="Windy Hill.mp3").json()
    an.post(f"/api/videos/{video.id}/music", files={"file": ("cu.mp3", OTHER_MP3, "audio/mpeg")})
    old_key = db.get(Video, video.id).music_key

    payload = an.post(f"/api/videos/{video.id}/music/from-library", json={"track_id": track["id"]}).json()
    assert payload["music"]["name"] == "Windy Hill" and payload["music_volume"] == 25
    assert an.get(payload["music"]["url"]).content == MP3
    chosen = db.get(Video, video.id)
    assert chosen.music_key.startswith(f"videos/{video.id}/music-") and not storage.exists(old_key)
    # Copied, not moved: the track still plays and another video can take it too.
    assert an.get(track["url"]).content == MP3
    second = make_video(db, storage, me)
    assert an.post(f"/api/videos/{second.id}/music/from-library", json={"track_id": track["id"]}).status_code == 200

    # Editing or deleting the track never changes the video.
    an.patch(f"/api/music/{track['id']}", json={"name": "Tên khác"})
    assert an.delete(f"/api/music/{track['id']}").json() == {"ok": True}
    assert an.get(f"/api/music/{track['id']}/audio.mp3").status_code == 404
    assert an.get(f"/api/videos/{video.id}").json()["music"]["name"] == "Windy Hill"
    assert storage.path(chosen.music_key).read_bytes() == MP3


def test_choosing_a_missing_track_keeps_the_video_music(an, db, me, storage):
    video = make_video(db, storage, me)
    an.post(f"/api/videos/{video.id}/music", files={"file": ("cu.mp3", OTHER_MP3, "audio/mpeg")})
    response = an.post(f"/api/videos/{video.id}/music/from-library", json={"track_id": 999999})
    assert response.status_code == 404 and response.json()["code"] == "track_not_found"
    assert an.get(f"/api/videos/{video.id}").json()["music"]["name"] == "cu.mp3"


def test_a_track_whose_file_is_gone_is_refused(an, db, me, storage):
    video = make_video(db, storage, me)
    track = add_track(an).json()
    storage.delete(db.get(MusicTrack, track["id"]).storage_key)
    response = an.post(f"/api/videos/{video.id}/music/from-library", json={"track_id": track["id"]})
    assert response.status_code == 404 and response.json()["code"] == "track_not_found"
    assert db.get(Video, video.id).music_key is None


def test_a_locked_video_cannot_take_a_track(an, db, me, storage):
    video = make_video(db, storage, me)
    track = add_track(an).json()
    assert an.post(f"/api/videos/{video.id}/render").status_code == 200
    response = an.post(f"/api/videos/{video.id}/music/from-library", json={"track_id": track["id"]})
    assert response.status_code == 409
    assert db.get(Video, video.id).music_key is None


def test_library_needs_a_login(app, an, db, me, storage):
    video = make_video(db, storage, me)
    track = add_track(an).json()
    # The web app's Origin, so the CSRF guard lets the request through and only the login check can refuse it.
    anonymous = client_for(app)
    for response in (
        anonymous.get("/api/music"),
        anonymous.get("/api/music/options"),
        anonymous.get(f"/api/music/{track['id']}/audio.mp3"),
        anonymous.post("/api/music", data={"topics": ["gan"], "mood": "piano"},
                       files={"file": ("a.mp3", MP3, "audio/mpeg")}),
        anonymous.patch(f"/api/music/{track['id']}", json={"name": "x"}),
        anonymous.delete(f"/api/music/{track['id']}"),
        anonymous.post(f"/api/videos/{video.id}/music/from-library", json={"track_id": track["id"]}),
    ):
        assert response.status_code == 401, response.request.url
    assert [row["name"] for row in an.get("/api/music").json()] == ["Windy Hill"]
    assert db.get(Video, video.id).music_key is None
