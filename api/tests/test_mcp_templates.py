"""Part 5 of docs/specs/per-user-settings-ownership: the assistant sees the member's "Mẫu dựng" (their own and the
topic groups'), puts one on a video as "Tự dựng" does, and saves a video's look as one of the member's own."""

from conftest import client_for, first_topic, login, make_user, make_video
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload, rpc  # noqa: F401 (mcp_client is a fixture)

from reels_api.models import EditTemplate, SceneSound
from reels_api.videos import split_scenes

X = {
    "transitions": ["circle"],
    "scene_sounds": [{"sound": "pop", "start": 0.0, "volume": "soft"}],
    "end_layers": [
        {
            "kind": "text",
            "text": "Theo dõi nhé",
            "sticker": "",
            "start": 0.5,
            "seconds": 2,
            "x": 540,
            "y": 400,
            "size": "medium",
            "style": "yellow",
            "animation": "fade",
        }
    ],
}


def save_as(client, token, video_id: int, name: str) -> dict:
    """`call` takes the tool's name as its own `name`, so the tool's `name` argument goes in by hand."""
    response = rpc(
        client,
        token,
        "tools/call",
        {"name": "save_video_as_template", "arguments": {"video_id": video_id, "name": name}},
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


def test_the_three_tools_are_listed_with_read_and_write_scopes(mcp_client, db):  # noqa: F811
    _, _, tokens, _ = grant(mcp_client, db)
    tools = {
        tool["name"]: tool for tool in rpc(mcp_client, tokens["access_token"], "tools/list").json()["result"]["tools"]
    }
    scopes = {name: tools[name]["_meta"]["securitySchemes"][0]["scopes"] for name in tools}
    assert scopes["list_templates"] == ["reels:read"]
    assert scopes["apply_template_to_video"] == ["reels:read", "reels:write"]
    assert scopes["save_video_as_template"] == ["reels:read", "reels:write"]
    assert tools["list_templates"]["annotations"]["readOnlyHint"] is True


def test_the_list_holds_the_apps_the_members_own_and_the_groups_with_what_each_does(mcp_client, db):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    other = make_user(db, email="binh@doi.vn", name="Trần Bình")
    mine = EditTemplate(name="Của tôi", data=X, created_by_id=user.id)
    groups = EditTemplate(name="Của nhóm", data={"transitions": ["flash"]}, created_by_id=other.id)
    hidden = EditTemplate(name="Riêng của Bình", data={"transitions": ["fade"]}, created_by_id=other.id)
    db.add_all([mine, groups, hidden])
    db.flush()
    group = first_topic(db)
    group.edit_templates.append(groups)
    group.edit_template_default = groups.id
    db.commit()

    listed = payload(call(mcp_client, tokens["access_token"], "list_templates"))["templates"]
    by_name = {item["name"]: item for item in listed}
    assert set(by_name) == {"Gợi ý của app", "Của tôi", "Của nhóm"}
    assert by_name["Của tôi"]["scope"] == "personal" and by_name["Của tôi"]["groups"] == []
    assert by_name["Của nhóm"]["scope"] == "group"
    assert by_name["Của nhóm"]["groups"] == [{"id": group.id, "name": group.name, "default": True}]
    assert by_name["Gợi ý của app"]["scope"] == "app"
    parts = by_name["Của tôi"]
    assert parts["transitions"] == ["Mở vòng tròn"] and parts["scene_sounds"] is True and parts["end_layer"] is True
    assert parts["video_mode"] is None  # a template fits either kind of video
    assert by_name["Gợi ý của app"]["end_layer"] is True and by_name["Của nhóm"]["scene_sounds"] is False


def test_putting_a_template_on_a_video_changes_that_video_only(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    template = EditTemplate(name="Của tôi", data=X, created_by_id=user.id)
    db.add(template)
    db.commit()
    video = make_video(db, storage, user, scene_count=2)
    untouched = make_video(db, storage, user, scene_count=2)
    applied = call(
        mcp_client, tokens["access_token"], "apply_template_to_video", video_id=video.id, template_id=template.id
    )
    assert not applied.get("isError"), applied
    assert payload(applied)["edit_template"] == {"id": template.id, "name": "Của tôi", "source": "video"}
    _, scenes = split_scenes(db, video)
    assert [scene.transition for scene in scenes] == ["circle", "circle"]
    assert db.scalars(select(SceneSound.sound).where(SceneSound.scene_id == scenes[0].id)).all() == ["pop"]
    # The script's last scene is its call to action: the template's end line stays off it.
    assert scenes[-1].layers == []
    assert [scene.transition for scene in split_scenes(db, untouched)[1]] == [None, None]

    # "app" works too, and a template that does not exist is refused without changing anything.
    assert not call(
        mcp_client, tokens["access_token"], "apply_template_to_video", video_id=video.id, template_id="app"
    ).get("isError")
    assert call(mcp_client, tokens["access_token"], "apply_template_to_video", video_id=video.id, template_id=9999)[
        "isError"
    ]


def test_a_videos_look_is_saved_as_the_members_own_template_and_a_taken_name_is_refused(mcp_client, app, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    video = make_video(db, storage, user, scene_count=2)
    for scene in split_scenes(db, video)[1]:
        scene.transition = "flash"
    db.commit()
    saved = save_as(mcp_client, tokens["access_token"], video.id, "Chớp nhanh")
    assert not saved.get("isError"), saved
    row = db.scalar(select(EditTemplate).where(EditTemplate.name == "Chớp nhanh"))
    assert row.created_by_id == user.id and row.data["transitions"] == ["flash", "flash"]
    listed = payload(call(mcp_client, tokens["access_token"], "list_templates"))["templates"]
    assert any(item["name"] == "Chớp nhanh" and item["scope"] == "personal" for item in listed)

    # Seen on the web's Mẫu dựng page too.
    web = client_for(app)
    login(web, email=user.email)
    assert any(item["name"] == "Chớp nhanh" for item in web.get("/api/edit-templates").json()["templates"])

    again = save_as(mcp_client, tokens["access_token"], video.id, "Chớp nhanh")
    assert again["isError"]
    db.refresh(row)
    assert row.data["transitions"] == ["flash", "flash"]
    assert db.scalars(select(EditTemplate).where(EditTemplate.name == "Chớp nhanh")).all() == [row]
