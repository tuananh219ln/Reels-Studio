"""A topic group's "Chuyển động & âm thanh": how its new videos move and sound, over their maker's defaults
(docs/decisions/2026-11-28-group-video-look.md)."""

import pytest
from conftest import client_for, first_topic, login, make_user

from reels_api import text_looks, video_options
from reels_api.models import KnowledgeTopic, MusicTrack, UserVideoDefaults, Video

LOOK = {
    "transition": "blur",
    "motion": "punch_in",
    "zoom": "extreme",
    "voice_speed": 1.15,
    "voice_volume": 80,
    "voice_pause": 0.7,
    "ducking": True,
    "music_volume": 12,
    "voice_enabled": False,
}
# The settings held in a video's options; the others are columns of the video.
IN_OPTIONS = [name for name in LOOK if name not in ("music_volume", "voice_enabled")]


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def shown(response, group_id: int) -> dict:
    [topic] = [topic for topic in response.json()["topics"] if topic["id"] == group_id]
    return topic


def new_video(an, group_id: int) -> dict:
    made = an.post("/api/videos", json={"topic": "canh chua", "knowledge_topic_id": group_id})
    assert made.status_code == 201, made.json()
    return made.json()


# --- Without a database ---


def test_a_group_sets_only_motion_and_sound_and_every_value_is_checked():
    assert video_options.clean_group_video(LOOK) == LOOK
    for bad in ({"text_size": "small"}, {"voice_id": "abc"}, {"motion": "spin"}, {"music_volume": 101}, ["fade"]):
        with pytest.raises(video_options.OptionError):
            video_options.clean_group_video(bad)


def test_a_stored_value_no_longer_accepted_is_left_out_alone():
    group = KnowledgeTopic(name="Sức khỏe", video_look={"motion": "spin", "zoom": "light", "text_size": "small"})
    assert video_options.group_video(group) == {"zoom": "light"}
    assert video_options.group_video(KnowledgeTopic(name="Mới")) == {}
    assert video_options.group_video(None) == {}


def test_the_groups_music_is_a_track_from_a_second_or_none():
    assert video_options.clean_group_video({"music_track_id": 3, "music_start": 12.34}) == {
        "music_track_id": 3,
        "music_start": 12.3,
    }
    assert video_options.clean_group_video({"music_track_id": None}) == {"music_track_id": None}
    for bad in ({"music_track_id": 0}, {"music_start": -1}, {"music_start": 601}, {"music_start": "5"}):
        with pytest.raises(video_options.OptionError):
            video_options.clean_group_video(bad)


def test_the_text_looks_two_checkboxes_are_saved_and_never_written_by_the_ai():
    look = {"text_shade": True, "title_effects": False}
    assert text_looks.clean_look(look) == look
    assert text_looks.loose_look(look | {"text_size": "small"}) == {"text_size": "small"}


# --- With the database ---


def test_a_new_video_takes_the_groups_motion_and_sound_over_its_makers(an, db, me):
    db.add(UserVideoDefaults(user_id=me.id, value={"transition": "cut", "zoom": "light", "music_volume": 40}))
    db.commit()
    group = first_topic(db).id
    knowledge = an.get("/api/knowledge")
    assert shown(knowledge, group)["video_look"] is None
    start = knowledge.json()["default_video_look"]
    # Everything it may set but the maker's own track, which a group takes only when chosen.
    assert set(start) == set(video_options.GROUP_VIDEO_FIELDS) - {"music_track_id", "music_start"}
    assert start["transition"] == "cut"

    saved = an.patch(f"/api/knowledge/topics/{group}", json={"video_look": LOOK})
    assert saved.status_code == 200, saved.json()
    assert shown(saved, group)["video_look"] == LOOK

    made = new_video(an, group)
    assert {name: made["options"][name] for name in IN_OPTIONS} == {name: LOOK[name] for name in IN_OPTIONS}
    video = db.get(Video, made["id"])
    assert (video.music_volume, video.voice_enabled) == (12, False)

    cleared = an.patch(f"/api/knowledge/topics/{group}", json={"video_look": None})
    assert shown(cleared, group)["video_look"] is None
    again = new_video(an, group)
    assert (again["options"]["transition"], again["options"]["zoom"]) == ("cut", "light")
    assert db.get(Video, again["id"]).music_volume == 40
    # The video made while the group had its own keeps it.
    assert an.get(f"/api/videos/{made['id']}").json()["options"]["transition"] == "blur"


def test_what_a_group_does_not_set_stays_the_makers(an, db, me):
    db.add(UserVideoDefaults(user_id=me.id, value={"transition": "cut", "voice_speed": 1.3}))
    db.commit()
    group = first_topic(db).id
    an.patch(f"/api/knowledge/topics/{group}", json={"video_look": {"motion": "pan"}})
    options = new_video(an, group)["options"]
    assert (options["motion"], options["transition"], options["voice_speed"]) == ("pan", "cut", 1.3)


def test_a_wrong_value_is_refused_and_nothing_is_saved(an, db):
    group = first_topic(db).id
    for bad in ({"motion": "spin"}, {"captions": "word"}, {"voice_pause": 9}):
        refused = an.patch(f"/api/knowledge/topics/{group}", json={"video_look": bad})
        assert refused.status_code == 422, bad
    db.expire_all()
    assert db.get(KnowledgeTopic, group).video_look is None


def test_it_is_in_the_groups_history_copied_with_the_group_and_behind_its_edit_lock(an, app, db, me):
    group = first_topic(db)
    group.created_by_id, group.team_edit = me.id, False
    db.commit()
    an.patch(f"/api/knowledge/topics/{group.id}", json={"video_look": {"zoom": "strong"}})
    history = an.get(f"/api/edit-logs?entity_type=knowledge_topic&entity_id={group.id}").json()["entries"]
    assert history[0]["changes"]["video_look"] == {"old": None, "new": {"zoom": "strong"}}

    copied = an.post(f"/api/knowledge/topics/{group.id}/duplicate").json()["topics"]
    [copy] = [topic for topic in copied if topic["name"] == f"{group.name} (bản sao)"]
    assert copy["video_look"] == {"zoom": "strong"}

    make_user(db, email="binh@doi.vn", name="Bình")
    binh = client_for(app)
    login(binh, "binh@doi.vn")
    refused = binh.patch(f"/api/knowledge/topics/{group.id}", json={"video_look": None})
    assert refused.status_code == 403, refused.json()


def _track(db, storage, me, name: str) -> MusicTrack:
    key = f"music/{name}.mp3"
    storage.save_bytes(key, name.encode())
    track = MusicTrack(name=name, topics=["chung"], mood="piano", storage_key=key, created_by_id=me.id)
    db.add(track)
    db.commit()
    return track


def test_a_new_video_starts_with_the_groups_music_or_none_else_its_makers(an, db, me, storage):
    mine, theirs = _track(db, storage, me, "mine"), _track(db, storage, me, "group")
    db.add(UserVideoDefaults(user_id=me.id, value={"music_track_id": mine.id}))
    db.commit()
    group = first_topic(db).id
    url = f"/api/knowledge/topics/{group}"

    def music() -> tuple:
        video = db.get(Video, new_video(an, group)["id"])
        db.refresh(video)
        return video.music_name, video.music_start

    assert music() == ("mine", 0)
    saved = an.patch(url, json={"video_look": {"music_track_id": theirs.id, "music_start": 15}})
    assert saved.status_code == 200, saved.json()
    assert shown(saved, group)["video_look_track"]["name"] == "group"
    assert music() == ("group", 15)

    an.patch(url, json={"video_look": {"music_track_id": None}})
    assert music() == (None, 0)

    # A track claimed since leaves the maker's own; one claimed or unknown cannot be chosen.
    an.patch(url, json={"video_look": {"music_track_id": theirs.id, "music_start": 15}})
    theirs.claimed_on_youtube = True
    db.commit()
    assert music() == ("mine", 0)
    assert an.patch(url, json={"video_look": {"music_track_id": theirs.id}}).status_code == 409
    assert an.patch(url, json={"video_look": {"music_track_id": 999999}}).status_code == 404


def test_a_groups_look_saves_the_two_checkboxes_for_its_new_videos(an, db, me):
    group = first_topic(db).id
    saved = an.patch(f"/api/knowledge/topics/{group}", json={"text_look": {"text_shade": True, "title_effects": False}})
    assert saved.status_code == 200, saved.json()
    options = new_video(an, group)["options"]
    assert (options["text_shade"], options["title_effects"]) == (True, False)
