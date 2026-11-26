"""A group's "QC & duyệt", a video's "Không dùng tiêu đề", its "Lịch sử sửa" with "Hoàn tác", and "Video này được làm
như thế nào" (docs/decisions/2026-11-26-per-group-qc.md)."""

import pytest
from conftest import first_topic, login, make_user, make_video
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)
from test_publish import add_mp4

from reels_api import qc, qc_config, review
from reels_api.models import EditLog, Job, Scene
from reels_api.script_rules import SceneInput, check_script
from reels_api.videos import split_scenes

THREADS = {
    "title_required": False,
    "total_seconds": {"min": 45, "max": 100},
    "scene_count": {"min": 5, "max": 13},
    "channel_seconds": {"min": 60, "max": 90},
}


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def codes(db, video) -> list[str]:
    return [item["code"] for item in review.qc_report(db, video)["items"]]


def set_group(db, config) -> None:
    first_topic(db).qc_config = qc_config.clean(config)
    db.commit()


def title_scene(db, video) -> Scene:
    return split_scenes(db, video)[0]


# --- The group's settings ---


def test_cleaning_keeps_only_what_differs_from_the_defaults():
    assert qc_config.clean(None) is None
    assert qc_config.clean(qc_config.defaults()) is None, "the defaults saved as they are stay the app's"
    assert qc_config.clean({"title_required": False, "scene_count": {"min": 5, "max": 7}}) == {"title_required": False}
    assert qc_config.clean(THREADS) == THREADS
    assert qc_config.of(None) == qc_config.defaults() and not qc_config.is_set(None)
    assert qc_config.of(THREADS)["total_seconds"] == {"min": 45, "max": 100} and qc_config.is_set(THREADS)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"loudness": -14}, "Không có mục loudness"),
        ({"title_required": "no"}, "đúng hoặc sai"),
        ({"total_seconds": {"min": 60}}, "phải có min và max"),
        ({"total_seconds": {"min": 60, "max": 40}}, "min không lớn hơn max"),
        ({"total_seconds": {"min": 20, "max": 200}}, "từ 0 đến 150"),
        ({"scene_count": {"min": 5.5, "max": 9}}, "số nguyên"),
        ({"channel_seconds": {"min": 2, "max": 9}}, "tối thiểu 5"),
    ],
)
def test_cleaning_refuses_what_the_checks_could_not_use(value, message):
    with pytest.raises(qc_config.ConfigError, match=message):
        qc_config.clean(value)


def test_a_member_sets_the_groups_qc_and_it_is_in_the_history(an, db):
    group = first_topic(db)
    shown = an.patch(f"/api/knowledge/topics/{group.id}", json={"qc_config": THREADS})
    assert shown.status_code == 200, shown.text
    row = next(row for row in shown.json()["topics"] if row["id"] == group.id)
    assert row["qc_config"] == THREADS and row["qc_config_set"] is True
    history = an.get(f"/api/edit-logs?entity_type=knowledge_topic&entity_id={group.id}").json()["entries"]
    assert history[0]["changes"]["qc_config"] == {"old": None, "new": THREADS}
    refused = an.patch(f"/api/knowledge/topics/{group.id}", json={"qc_config": {"scene_count": {"min": 9, "max": 3}}})
    assert refused.status_code == 422 and "Số cảnh nội dung" in refused.text
    cleared = an.patch(f"/api/knowledge/topics/{group.id}", json={"qc_config": None})
    row = next(row for row in cleared.json()["topics"] if row["id"] == group.id)
    assert row["qc_config_set"] is False and row["qc_config"] == qc_config.defaults()


# --- The checks ---


def test_the_scripts_yellow_ranges_are_the_groups():
    scenes = [SceneInput(id=n, is_title=False, text="", seconds=8, has_image=True) for n in range(10)]
    default = [issue.message for issue in check_script(None, scenes, {}, []).warnings]
    assert any("nên trong khoảng 20–55 giây" in text for text in default)
    assert any("công thức kênh là 5–7 cảnh" in text for text in default)
    assert check_script(None, scenes, {}, [], (45, 100), (5, 13)).warnings == []


def test_a_group_without_a_title_lets_an_empty_title_through(db, me, storage):
    video = make_video(db, storage, me, scene_count=1, title_text="")
    add_mp4(db, storage, video, approved=False)
    assert "TITLE_EMPTY" in codes(db, video), "the app's default still asks for a title"
    set_group(db, {"title_required": False})
    assert "TITLE_EMPTY" not in codes(db, video)


def test_no_title_on_the_video_lets_it_through_in_a_group_that_asks_for_one(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    shown = an.patch(f"/api/videos/{video.id}", json={"no_title": True})
    assert shown.status_code == 200, shown.text
    assert shown.json()["no_title"] is True and shown.json()["title_required"] is True
    db.expire_all()
    assert title_scene(db, video).text == "" and video.kept_title
    add_mp4(db, storage, video, approved=False)
    assert "TITLE_EMPTY" not in codes(db, video)


def test_unticking_no_title_gives_the_kept_text_back_and_typing_a_title_unticks_it(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    before = title_scene(db, video).text
    an.patch(f"/api/videos/{video.id}", json={"no_title": True})
    back = an.patch(f"/api/videos/{video.id}", json={"no_title": False})
    assert back.json()["no_title"] is False
    db.expire_all()
    assert title_scene(db, video).text == before and video.kept_title is None

    an.patch(f"/api/videos/{video.id}", json={"no_title": True})
    typed = an.patch(f"/api/scenes/{title_scene(db, video).id}", json={"text": "TIÊU ĐỀ MỚI"})
    assert typed.json()["no_title"] is False
    db.expire_all()
    assert video.kept_title is None


def test_the_mp4_length_is_judged_against_the_groups_range_when_read(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    add_mp4(db, storage, video, approved=False)
    found = qc.check_length(70, qc.SHORT, qc.LONG)
    video.qc, video.mp4_seconds = {"status": "warn", "checks": [found]}, 70.0
    db.commit()
    assert "kênh nhắm 20–40 giây" in found["detail"]
    assert "MP4_QC" in codes(db, video)
    set_group(db, {"channel_seconds": {"min": 60, "max": 90}})
    assert "MP4_QC" not in codes(db, video), "a video rendered before the range changed follows the new one"
    shown = an.get(f"/api/videos/{video.id}").json()
    assert shown["mp4"]["qc"]["status"] == "pass"
    set_group(db, {"channel_seconds": {"min": 80, "max": 90}})
    assert "kênh nhắm 80–90 giây" in str(review.qc_report(db, video))


# --- "Lịch sử sửa" and "Hoàn tác" ---


def test_an_edit_is_in_the_videos_history_and_can_be_undone(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=2)
    scene = split_scenes(db, video)[1][0]
    old = scene.text
    an.patch(f"/api/scenes/{scene.id}", json={"text": "Chữ mới", "seconds": 5})
    an.patch(f"/api/videos/{video.id}", json={"caption": "caption mới"})
    story = an.get(f"/api/video-story/{video.id}").json()
    edit = story["history"][1]
    assert edit["source"] == "web" and edit["by"] == me.name
    assert {(row["place"], row["field"], row["new"]) for row in edit["changes"]} >= {("Cảnh 1", "Chữ", "Chữ mới")}

    undone = an.post(f"/api/video-story/{video.id}/undo/{edit['id']}")
    assert undone.status_code == 200, undone.text
    db.expire_all()
    assert (scene.text, scene.seconds) == (old, 4.0)
    assert video.caption == "caption mới", "only that edit is undone"
    entries = an.get(f"/api/video-story/{video.id}").json()["history"]
    assert entries[0]["action"] == "restore" and entries[0]["restored_from_id"] == edit["id"]
    assert next(entry for entry in entries if entry["id"] == edit["id"])["undone"] is True


def test_undo_refuses_when_the_place_was_edited_since(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    scene = split_scenes(db, video)[1][0]
    an.patch(f"/api/scenes/{scene.id}", json={"text": "Lần 1"})
    first = db.scalar(select(EditLog).where(EditLog.entity_id == video.id).order_by(EditLog.id.desc()))
    an.patch(f"/api/scenes/{scene.id}", json={"text": "Lần 2"})
    refused = an.post(f"/api/video-story/{video.id}/undo/{first.id}")
    assert (refused.status_code, refused.json()["code"]) == (409, "edited_since")
    db.expire_all()
    assert scene.text == "Lần 2"


def test_undoing_no_title_brings_the_title_back(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    before = title_scene(db, video).text
    an.patch(f"/api/videos/{video.id}", json={"no_title": True})
    edit = an.get(f"/api/video-story/{video.id}").json()["history"][0]
    assert {row["field"] for row in edit["changes"]} == {"Không dùng tiêu đề", "Chữ"}
    assert an.post(f"/api/video-story/{video.id}/undo/{edit['id']}").status_code == 200
    db.expire_all()
    assert (video.no_title, title_scene(db, video).text) == (False, before)


# --- "Video này được làm như thế nào" ---


def test_the_story_names_the_maker_the_voices_and_the_timeline(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=2)
    title, scenes = split_scenes(db, video)
    video.written_via, video.assistant_app = "assistant", "Muse"
    scenes[0].voice_text, scenes[0].voice_id = "Một", "vieneu:Huyền My"
    scenes[1].voice_text, scenes[1].voice_signature, scenes[1].voice_name = "Hai", "custom:abc", "canh-2.mp3"
    db.add(Job(video_id=video.id, kind="render", status="done", created_by_id=me.id))
    db.commit()
    story = an.get(f"/api/video-story/{video.id}").json()
    assert story["made"]["by"] == me.name and story["made"]["via"] == "Muse qua MCP" and story["made"]["free"]
    voices = {row["label"]: (row["source"], row["voice"]) for row in story["voices"]}
    assert voices["Cảnh 1"] == ("VieNeu", "Huyền My") and voices["Cảnh 2"] == ("MP3 tải lên", "canh-2.mp3")
    assert story["mixed_voices"] is True
    assert [row["kind"] for row in story["timeline"]][:2] == ["created", "job"]
    assert "Render: xong" in story["text"] and "Muse qua MCP" in story["text"]


# --- MCP ---


def test_an_assistant_sets_the_title_three_ways(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=1)
    picked = call(mcp_client, token, "set_video_title", video_id=video.id, option=2)
    assert not picked.get("isError"), picked
    db.expire_all()
    assert title_scene(db, video).text == "TIÊU ĐỀ 2"
    call(mcp_client, token, "set_video_title", video_id=video.id, text="Tự gõ")
    db.expire_all()
    assert title_scene(db, video).text == "Tự gõ"
    call(mcp_client, token, "set_video_title", video_id=video.id, no_title=True)
    db.expire_all()
    assert (video.no_title, title_scene(db, video).text) == (True, "")
    both = call(mcp_client, token, "set_video_title", video_id=video.id, text="a", no_title=False)
    assert both["isError"] and "đúng một" in str(both)
    history = db.scalars(select(EditLog).where(EditLog.entity_type == "video", EditLog.entity_id == video.id))
    assert {entry.source for entry in history} == {"mcp"}


def test_an_assistant_reads_and_edits_the_groups_qc_and_voice_format(mcp_client, db, storage):  # noqa: F811
    _, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    group = first_topic(db)
    read = payload(call(mcp_client, token, "get_qc_config", knowledge_topic_id=group.id))
    assert read["is_set"] is False and "bắt tiêu đề" in read["summary"]
    edited = payload(
        call(mcp_client, token, "update_qc_config", knowledge_topic_id=group.id, title_required=False, **THREADS_RANGES)
    )
    assert edited["qc_config"] == THREADS and edited["is_set"] is True
    reset = payload(call(mcp_client, token, "update_qc_config", knowledge_topic_id=group.id, reset=True))
    assert reset["is_set"] is False

    voices = {"mode": "single", "roles": [{"role": "all", "source": "provider", "voice": "vieneu:Huyền My"}]}
    saved = payload(call(mcp_client, token, "update_voice_format", knowledge_topic_id=group.id, voice_format=voices))
    assert saved["voice_format"]["roles"][0]["voice"] == "vieneu:Huyền My"
    db.expire_all()
    assert group.voice_format["mode"] == "single"
    bad = call(mcp_client, token, "update_voice_format", knowledge_topic_id=group.id, voice_format={"mode": "x"})
    assert bad["isError"]


THREADS_RANGES = {field: THREADS[field] for field in ("total_seconds", "scene_count", "channel_seconds")}


def test_an_assistant_loops_a_scenes_clip(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=1)
    scene = split_scenes(db, video)[1][0]
    scene.video_key, scene.video_seconds = f"videos/{video.id}/clip.mp4", 3.0
    db.commit()
    looped = call(mcp_client, token, "update_scene", scene_id=scene.id, video_loop=True)
    assert not looped.get("isError"), looped
    db.expire_all()
    assert scene.video_loop is True
