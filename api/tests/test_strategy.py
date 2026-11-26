"""A video's strategy and beats: validated, edited from the page (a changed text reaches its scene) and written by Muse
through MCP (docs/decisions/2026-11-26-strategy-beats.md)."""

import pytest
from conftest import login, make_user, make_video
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)
from test_publish import add_mp4

from reels_api import review
from reels_api.models import Job, Scene, VideoEvent
from reels_api.videos import split_scenes

STRATEGY = {
    "content_type": "hook_pain_solution",
    "audience": "Người 40+",
    "pain_point": "Sợ uống thuốc cả đời",
    "promise": "3 món dễ mua",
}


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def beats_of(db, video) -> list[dict]:
    title, scenes = split_scenes(db, video)
    return [
        {"id": "b1", "type": "hook", "start": 0, "end": 3, "text": "Mỡ máu cao?", "scene_ids": [title.id],
         "alt_hooks": ["Bác sĩ ít nói điều này", "90% bỏ lỡ món số 2"]},
        {"id": "b2", "type": "pain", "start": 3, "end": 7, "text": "Sợ uống thuốc", "scene_ids": []},
        {"id": "b3", "type": "cta", "start": 7, "end": 10, "text": "Lưu lại", "scene_ids": [scenes[0].id],
         "affiliate_product_id": None},
    ]  # fmt: skip


def put(an, video, **body):
    return an.put(f"/api/strategy/{video.id}", json=body)


def test_the_catalog_lists_the_content_and_beat_types(an):
    found = an.get("/api/strategy/catalog").json()
    assert [row["code"] for row in found["content_types"]][0] == "hook_pain_solution"
    assert {"hook", "cta", "turning_point"} <= {row["code"] for row in found["beat_types"]}


def test_a_video_starts_without_them_and_keeps_what_is_saved(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=2)
    assert an.get(f"/api/videos/{video.id}").json()["beats"] is None
    answer = put(an, video, strategy=STRATEGY, beats=beats_of(db, video))
    assert answer.status_code == 200, answer.text
    detail = an.get(f"/api/videos/{video.id}").json()
    assert detail["strategy"] == STRATEGY and [b["id"] for b in detail["beats"]] == ["b1", "b2", "b3"]
    assert detail["beats"][0]["alt_hooks"] == ["Bác sĩ ít nói điều này", "90% bỏ lỡ món số 2"]
    assert db.scalar(select(VideoEvent.type).where(VideoEvent.video_id == video.id)) == "strategy_saved"


def test_only_the_part_sent_is_replaced(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=2)
    put(an, video, strategy=STRATEGY, beats=beats_of(db, video))
    put(an, video, strategy={**STRATEGY, "promise": "5 món"})
    detail = an.get(f"/api/videos/{video.id}").json()
    assert detail["strategy"]["promise"] == "5 món" and len(detail["beats"]) == 3


@pytest.mark.parametrize(
    "change",
    [
        {"strategy": {**STRATEGY, "content_type": "nope"}},
        {"strategy": {**STRATEGY, "audience": "x" * 301}},
        {"beats": [{"id": "b1", "type": "nope", "start": 0, "end": 1, "text": "a", "scene_ids": []}]},
        {"beats": [{"id": "b1", "type": "hook", "start": 5, "end": 1, "text": "a", "scene_ids": []}]},
        {"beats": [{"id": "b1", "type": "hook", "start": 0, "end": 1, "text": "a", "scene_ids": [999999]}]},
        {"beats": [{"id": "b1", "type": "pain", "start": 0, "end": 1, "text": "a", "scene_ids": []}] * 2},
    ],
)
def test_a_wrong_value_is_refused_and_nothing_is_saved(an, db, me, storage, change):
    video = make_video(db, storage, me, scene_count=1)
    answer = put(an, video, **change)
    assert (answer.status_code, answer.json()["code"]) == (422, "invalid_value")
    assert an.get(f"/api/videos/{video.id}").json()["beats"] is None


def test_another_videos_scene_cannot_be_named(an, db, me, storage):
    video, other = make_video(db, storage, me, scene_count=1), make_video(db, storage, me, scene_count=1)
    stranger = split_scenes(db, other)[0].id
    beat = {"id": "b1", "type": "hook", "start": 0, "end": 1, "text": "a", "scene_ids": [stranger]}
    assert put(an, video, beats=[beat]).status_code == 422


def test_a_changed_beat_text_reaches_its_scene_and_outdates_the_mp4(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=2)
    add_mp4(db, storage, video)
    beats = beats_of(db, video)
    put(an, video, strategy=STRATEGY, beats=beats)
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is False
    beats[0]["text"] = "Bác sĩ ít nói điều này"
    beats[1]["text"] = "Nỗi đau đổi chữ, không có cảnh"
    answer = put(an, video, beats=beats)
    assert answer.status_code == 200, answer.text
    db.expire_all()
    assert split_scenes(db, video)[0].text == "Bác sĩ ít nói điều này"
    detail = an.get(f"/api/videos/{video.id}").json()
    assert detail["mp4_outdated"] is True and detail["beats"][1]["text"].startswith("Nỗi đau đổi chữ")


def test_the_first_save_leaves_the_scenes_as_they_are(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    before = split_scenes(db, video)[0].text
    put(an, video, beats=beats_of(db, video))
    db.expire_all()
    assert split_scenes(db, video)[0].text == before


def test_a_video_with_a_job_running_cannot_change(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    db.add(Job(video_id=video.id, kind="render", status="running", created_by_id=me.id))
    db.commit()
    assert put(an, video, strategy=STRATEGY).status_code == 409


def test_the_review_shows_a_beat_without_a_scene_and_tags_scene_items_with_their_beat(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    add_mp4(db, storage, video, approved=False)
    beats = beats_of(db, video)
    put(an, video, beats=beats)
    db.expire_all()
    items = review.qc_report(db, video)["items"]
    empty = [item for item in items if item["code"] == "BEAT_WITHOUT_SCENE"]
    assert [item["beat"] for item in empty] == ["b2"] and empty[0]["level"] == "warn"
    tagged = [item for item in items if item.get("scene_id") == beats[0]["scene_ids"][0]]
    assert all(item["beat"] == "b1" for item in tagged)


def test_muse_writes_them_without_touching_the_scenes(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    video = make_video(db, storage, me, scene_count=2)
    beats = beats_of(db, video)
    done = payload(
        call(
            mcp_client, tokens["access_token"], "set_video_strategy", video_id=video.id, strategy=STRATEGY, beats=beats
        )
    )
    assert done["strategy"] == STRATEGY and done["editor_url"].endswith(f"/videos/{video.id}")
    beats[0]["text"] = "Muse đổi nhịp"
    call(mcp_client, tokens["access_token"], "set_video_strategy", video_id=video.id, beats=beats)
    db.expire_all()
    assert split_scenes(db, video)[0].text != "Muse đổi nhịp" and video.beats[0]["text"] == "Muse đổi nhịp"
    wrong = call(
        mcp_client, tokens["access_token"], "set_video_strategy", video_id=video.id, strategy={"content_type": "x"}
    )
    assert wrong["isError"] is True and "danh mục" in wrong["content"][0]["text"]
    assert db.scalar(select(Scene.id).where(Scene.video_id == video.id)) is not None
