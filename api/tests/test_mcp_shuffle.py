"""MCP "Nhân bản xáo cảnh": the web's shuffled copies, then the assistant writes each copy a new title with "Sửa cảnh"
(docs/decisions/2026-11-17-shuffle-copies.md)."""

from conftest import make_video
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload, rpc  # noqa: F401  (mcp_client is a fixture)

from reels_api.models import Job, Scene, Video


def test_the_tool_is_listed_as_a_write_tool(mcp_client, db):  # noqa: F811
    _, _, tokens, _ = grant(mcp_client, db)
    tools = {
        tool["name"]: tool for tool in rpc(mcp_client, tokens["access_token"], "tools/list").json()["result"]["tools"]
    }
    shuffled = tools["shuffle_duplicate_video"]
    assert shuffled["inputSchema"]["required"] == ["video_id"]
    assert {"count", "lock_last", "pinned_scene_ids", "renumber"} <= set(shuffled["inputSchema"]["properties"])
    assert shuffled["annotations"]["readOnlyHint"] is False and shuffled["annotations"]["openWorldHint"] is False


def test_copies_are_made_and_their_titles_changed_through_update_scene(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, me, scene_count=4)
    scenes = db.scalars(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position)
    ).all()
    for number, scene in enumerate(scenes, start=1):
        scene.text = f"{number}. Món {number}"
    db.commit()
    last = scenes[-1].id

    answer = call(mcp_client, token, "shuffle_duplicate_video", video_id=video.id, count=3, pinned_scene_ids=[last])

    assert not answer.get("isError"), answer
    result = payload(answer)
    assert len(result["copies"]) == 3 and result["renumbered"] is True
    assert result["used_titles"] == ["5 MÓN GIÚP XƯƠNG CHẮC KHỎE"]
    db.expire_all()
    for copy in result["copies"]:
        row = db.get(Video, copy["id"])
        assert row.shuffled_from_id == video.id and row.created_by_id == me.id and row.mp4_key is None
        assert copy["editor_url"].endswith(f"/videos/{row.id}")
        assert [text[:2] for text in copy["scenes"]] == ["1.", "2.", "3.", "4."]
        assert copy["scenes"][-1] == "4. Món 4"
    made_ids = [copy["id"] for copy in result["copies"]]
    assert db.scalars(select(Job).where(Job.video_id.in_(made_ids))).all() == []

    first = result["copies"][0]
    edited = call(mcp_client, token, "update_scene", scene_id=first["title_scene_id"], text="XƯƠNG CHẮC NHỜ 5 MÓN NÀY")
    assert not edited.get("isError"), edited
    detail = call(mcp_client, token, "get_video", video_id=first["id"])
    assert payload(detail)["title_review"] is False
    again = payload(call(mcp_client, token, "shuffle_duplicate_video", video_id=video.id, count=1))
    assert "XƯƠNG CHẮC NHỜ 5 MÓN NÀY" in again["used_titles"]


def test_copies_get_the_dish_comments_in_their_new_order(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    video = make_video(db, storage, me, scene_count=4)
    scenes = db.scalars(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position)
    ).all()
    for number, scene in enumerate(scenes, start=1):
        scene.text = f"{number}. Món {number}"
    video.extra_comments = [f"{number}. Món {number}: cách làm và ai nên hỏi bác sĩ" for number in range(1, 5)]
    db.commit()

    result = payload(call(mcp_client, tokens["access_token"], "shuffle_duplicate_video", video_id=video.id, count=2))

    db.expire_all()
    for copy in result["copies"]:
        dishes = [text.split(". ", 1)[1] for text in copy["scenes"]]
        assert db.get(Video, copy["id"]).extra_comments == [
            f"{place}. {dish}: cách làm và ai nên hỏi bác sĩ" for place, dish in enumerate(dishes, start=1)
        ]
