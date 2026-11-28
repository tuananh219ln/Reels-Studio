"""A topic group's "Chuyển động & âm thanh": how its new videos move and sound, over their maker's defaults
(docs/decisions/2026-11-28-group-video-look.md)."""

import pytest
from conftest import client_for, first_topic, login, make_user

from reels_api import video_options
from reels_api.models import KnowledgeTopic, UserVideoDefaults, Video

LOOK = {
    "transition": "blur",
    "motion": "punch_in",
    "zoom": "extreme",
    "voice_speed": 1.15,
    "voice_volume": 80,
    "voice_pause": 0.7,
    "ducking": True,
    "music_volume": 12,
}


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


# --- With the database ---


def test_a_new_video_takes_the_groups_motion_and_sound_over_its_makers(an, db, me):
    db.add(UserVideoDefaults(user_id=me.id, value={"transition": "cut", "zoom": "light", "music_volume": 40}))
    db.commit()
    group = first_topic(db).id
    knowledge = an.get("/api/knowledge")
    assert shown(knowledge, group)["video_look"] is None
    start = knowledge.json()["default_video_look"]
    assert set(start) == set(video_options.GROUP_VIDEO_FIELDS) and start["transition"] == "cut"

    saved = an.patch(f"/api/knowledge/topics/{group}", json={"video_look": LOOK})
    assert saved.status_code == 200, saved.json()
    assert shown(saved, group)["video_look"] == LOOK

    made = new_video(an, group)
    assert {name: made["options"][name] for name in LOOK if name != "music_volume"} == {
        name: value for name, value in LOOK.items() if name != "music_volume"
    }
    assert db.get(Video, made["id"]).music_volume == 12

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
