"""Each member's own "Thiết lập mặc định": what their new videos start with, the app's built-in defaults until they
set their own (brief docs/specs/chu-thuong-ca-nhan-hoa, part B1; part 3 of docs/specs/per-user-settings-ownership
took the team's level away)."""

import pytest
from alembic import command
from alembic.config import Config
from conftest import API_DIR, client_for, first_topic, login, make_user
from sqlalchemy import text
from test_music_library import add_track

from reels_api import video_options
from reels_api.models import AppSetting

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


def test_a_member_without_their_own_defaults_uses_the_apps_built_in_ones(an, db):
    mine = an.get(MINE).json()
    assert mine["own"] is False and mine["owner"] == "Nguyễn Văn An"
    assert mine["transition"] == video_options.DEFAULTS["transition"] and mine["music_track"] is None
    assert new_video(an, db)["options"] == video_options.DEFAULTS


def test_the_teams_old_defaults_reach_no_new_video_and_cannot_be_edited_any_more(an, db):
    """Part 3: no level above the member. What the team's defaults held before is left unread."""
    db.add(AppSetting(key=video_options.DEFAULTS_KEY, value={"transition": "slide", "zoom": "strong"}))
    db.commit()
    assert new_video(an, db)["options"]["transition"] == video_options.DEFAULTS["transition"]
    assert an.get(MINE).json()["zoom"] == video_options.DEFAULTS["zoom"]
    assert an.get(TEAM).status_code in (404, 405)
    assert an.put(TEAM, json={"values": {"transition": "cut"}}).status_code in (404, 405)


def test_a_members_own_defaults_reach_only_their_new_videos(an, binh, db):
    saved = an.put(MINE, json={"values": {"voice_speed": 1.2, "text_case": "keep", "voice_enabled": False}}).json()
    assert saved["own"] is True and (saved["voice_speed"], saved["text_case"]) == (1.2, "keep")

    mine = new_video(an, db)
    assert (mine["options"]["voice_speed"], mine["options"]["text_case"], mine["voice_enabled"]) == (1.2, "keep", False)
    theirs = new_video(binh, db)
    assert (theirs["options"]["voice_speed"], theirs["options"]["text_case"]) == (1.0, "upper")
    assert binh.get(MINE).json()["own"] is False

    # A teammate's own change never reaches them.
    binh.put(MINE, json={"values": {"transition": "cut"}})
    assert new_video(an, db)["options"]["transition"] == video_options.DEFAULTS["transition"]
    assert new_video(binh, db)["options"]["transition"] == "cut"


def test_a_member_goes_back_to_the_apps_built_in_defaults(an, db):
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


def test_the_migration_gives_members_without_their_own_a_copy_of_the_teams(engine):
    """Migration 0067: at the switch, a member with no defaults of their own gets the team's as theirs, so what their
    new videos start with does not change; one with their own keeps them."""
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))
    config.attributes["configure_logger"] = False
    command.downgrade(config, "0066")
    try:
        with engine.begin() as connection:
            ids = [
                connection.scalar(
                    text(
                        "INSERT INTO users (email, name, password_hash, must_change_password, is_active) "
                        "VALUES (:email, 'x', 'x', false, true) RETURNING id"
                    ),
                    {"email": email},
                )
                for email in ("mig-a@doi.vn", "mig-b@doi.vn")
            ]
            connection.execute(
                text("INSERT INTO app_settings (key, value) VALUES ('video_defaults', '{\"transition\": \"slide\"}')")
            )
            connection.execute(
                text('INSERT INTO user_video_defaults (user_id, value) VALUES (:id, \'{"zoom": "strong"}\')'),
                {"id": ids[1]},
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            rows = dict(
                connection.execute(
                    text("SELECT user_id, value FROM user_video_defaults WHERE user_id = ANY(:ids)"), {"ids": ids}
                ).all()
            )
        assert rows == {ids[0]: {"transition": "slide"}, ids[1]: {"zoom": "strong"}}
    finally:
        command.upgrade(config, "head")
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM users WHERE email LIKE 'mig-%@doi.vn'"))
            connection.execute(text("DELETE FROM app_settings WHERE key = 'video_defaults'"))
