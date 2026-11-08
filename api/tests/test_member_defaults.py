"""Each member's own "Thiết lập mặc định": what their new videos start with, the team's defaults until they set
their own (brief docs/specs/chu-thuong-ca-nhan-hoa, part B1)."""

import pytest
from conftest import client_for, first_topic, login, make_user
from test_music_library import add_track

from reels_api import video_options

MINE = "/api/settings/my-video-defaults"
TEAM = "/api/settings/video-defaults"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def binh(db, app):
    other = make_user(db, email="binh@doi.vn", name="Trần Bình")
    client = client_for(app)
    login(client, email=other.email)
    return client


def new_video(client, db) -> dict:
    return client.post("/api/videos", json={"topic": "tim mạch", "knowledge_topic_id": first_topic(db).id}).json()


def test_a_member_without_their_own_defaults_uses_the_teams(an, db):
    an.put(TEAM, json={"values": {"transition": "slide"}})
    mine = an.get(MINE).json()
    assert mine["own"] is False and mine["owner"] == "Nguyễn Văn An"
    assert mine["transition"] == "slide" and mine["music_track"] is None
    assert new_video(an, db)["options"]["transition"] == "slide"


def test_a_members_own_defaults_reach_only_their_new_videos_and_stay_when_the_teams_change(an, binh, db):
    saved = an.put(MINE, json={"values": {"voice_speed": 1.2, "text_case": "keep", "voice_enabled": False}}).json()
    assert saved["own"] is True and (saved["voice_speed"], saved["text_case"]) == (1.2, "keep")

    mine = new_video(an, db)
    assert (mine["options"]["voice_speed"], mine["options"]["text_case"], mine["voice_enabled"]) == (1.2, "keep", False)
    theirs = new_video(binh, db)
    assert (theirs["options"]["voice_speed"], theirs["options"]["text_case"]) == (1.0, "upper")
    assert binh.get(MINE).json()["own"] is False

    # The team's defaults still start every member who has none of their own; a member's own are theirs to change.
    an.put(TEAM, json={"values": {"transition": "cut"}})
    assert new_video(binh, db)["options"]["transition"] == "cut"
    assert new_video(an, db)["options"]["transition"] == "fade"


def test_a_member_goes_back_to_the_teams_defaults(an, db):
    an.put(MINE, json={"values": {"zoom": "strong"}})
    back = an.delete(MINE).json()
    assert back["own"] is False and back["zoom"] == video_options.DEFAULTS["zoom"]
    assert new_video(an, db)["options"]["zoom"] == video_options.DEFAULTS["zoom"]


def test_a_members_default_music_reaches_their_new_videos_only(an, binh, db, storage):
    added = add_track(an, filename="Windy Hill.mp3", topics=("chung",))
    assert added.status_code == 200, added.text
    track = added.json()
    saved = an.put(MINE, json={"values": {"music_track_id": track["id"]}}).json()
    assert saved["music_track"]["name"] == "Windy Hill"
    assert new_video(an, db)["music"]["name"] == "Windy Hill"
    assert new_video(binh, db)["music"] is None


def test_wrong_values_are_refused_and_nothing_is_saved(an):
    assert an.put(MINE, json={"values": {"text_case": "lower"}}).status_code == 422
    assert an.put(MINE, json={"values": {"music_track_id": 999999}}).status_code == 404
    assert an.get(MINE).json()["own"] is False
