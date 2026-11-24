"""MCP "Nhân bản y hệt" and "Thêm vào hàng chờ": the web's own rules, so a winning video is copied to another Page
with that Page's logo, rendered, then queued for the Page's next free posting time (decisions 2026-11-15)."""

from datetime import timedelta

from conftest import first_topic, make_user, make_video
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload, rpc  # noqa: F401  (mcp_client is a fixture)
from test_page_queue import add_mp4, page

from reels_api import page_queue
from reels_api.models import (
    AffiliateProduct,
    Brand,
    KnowledgeTopic,
    McpConnection,
    PageQueueItem,
    Publication,
    Scene,
    SceneLayer,
    Video,
    VideoAffiliateProduct,
)
from reels_api.sessions import now


def brand(db, owner, name, fanpage=None, logo=True) -> Brand:
    row = Brand(
        name=name,
        slug=name.lower().replace(" ", "-"),
        owner_id=owner.id,
        fanpage_id=fanpage.id if fanpage else None,
        logo_badge_path=f"brands/{name}.png" if logo else None,
    )
    db.add(row)
    db.commit()
    return row


def other_group(db) -> KnowledgeTopic:
    group = KnowledgeTopic(name="Nhóm test")
    db.add(group)
    db.commit()
    return group


def product(db, user, name="Nồi hầm") -> AffiliateProduct:
    row = AffiliateProduct(
        knowledge_topic_id=first_topic(db).id,
        name=name,
        commission_rate=8,
        status="approved",
        created_by_id=user.id,
        shop_name="Shop",
        shop_type="mall",
        rating=4.9,
        sold=1000,
        price=200000,
    )
    db.add(row)
    db.commit()
    return row


def test_both_tools_are_listed_with_their_optional_fields(mcp_client, db):  # noqa: F811
    _, _, tokens, _ = grant(mcp_client, db)
    tools = {
        tool["name"]: tool for tool in rpc(mcp_client, tokens["access_token"], "tools/list").json()["result"]["tools"]
    }
    copy, queue = tools["duplicate_video"], tools["schedule_video"]
    assert copy["inputSchema"]["required"] == ["video_id"]
    assert {"knowledge_topic_id", "fanpage_id"} <= set(copy["inputSchema"]["properties"])
    assert queue["inputSchema"]["required"] == ["video_id"] and "fanpage_id" in queue["inputSchema"]["properties"]
    assert copy["annotations"]["readOnlyHint"] is False and copy["annotations"]["openWorldHint"] is False
    assert queue["annotations"]["openWorldHint"] is True


def test_a_teammates_video_is_copied_into_another_group_with_the_target_pages_logo(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    teammate = make_user(db, email="binh@doi.vn", name="Trần Bình")
    source = make_video(db, storage, teammate, scene_count=2)
    first = db.scalar(select(Scene).where(Scene.video_id == source.id, Scene.is_title.is_(False)))
    db.add(SceneLayer(scene_id=first.id, kind="text", text="Ghi chú", position=0))
    theirs = brand(db, teammate, "Ăn Ngon Sống Khỏe")
    source.options = {**(source.options or {}), "brand_id": theirs.id, "logo_enabled": True}
    db.add(VideoAffiliateProduct(video_id=source.id, product_id=product(db, teammate).id))
    add_mp4(db, storage, source)
    target = page(db, me, "Ăn Ngon Mỗi Ngày", page_id="999")
    mine = brand(db, me, "Ăn Ngon Mỗi Ngày", fanpage=target)
    group = other_group(db)

    answer = call(
        mcp_client,
        tokens["access_token"],
        "duplicate_video",
        video_id=source.id,
        knowledge_topic_id=group.id,
        fanpage_id=target.id,
    )

    assert not answer.get("isError"), answer
    result = payload(answer)
    db.expire_all()
    copy = db.get(Video, result["id"])
    assert result["editor_url"].endswith(f"/videos/{copy.id}")
    assert copy.name.endswith(" (bản 1)") and copy.created_by_id == me.id
    assert copy.knowledge_topic_id == group.id and source.knowledge_topic_id != group.id
    assert copy.mp4_key is None and copy.rendered_signature is None
    assert (copy.options["brand_id"], copy.options["logo_enabled"]) == (mine.id, True)
    assert result["brand"]["id"] == mine.id and result["logo_enabled"] is True
    assert len(result["scenes"]) == 2
    assert db.scalar(select(SceneLayer.text).join(Scene).where(Scene.video_id == copy.id)) == "Ghi chú"
    # The teammate's product came along: whose commission it earns is said.
    assert [row["name"] for row in result["products"]] == ["Nồi hầm"] and result["commission_warnings"]
    # The source is untouched.
    assert source.options["brand_id"] == theirs.id and source.mp4_key


def test_without_a_group_or_page_the_copy_keeps_the_sources(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    source = make_video(db, storage, me, scene_count=1)
    answer = call(mcp_client, tokens["access_token"], "duplicate_video", video_id=source.id)
    assert not answer.get("isError"), answer
    copy = db.get(Video, payload(answer)["id"])
    assert copy.knowledge_topic_id == source.knowledge_topic_id and copy.options == source.options


def test_a_copy_that_cannot_be_made_whole_leaves_nothing_behind(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    teammate = make_user(db, email="binh@doi.vn", name="Trần Bình")
    source = make_video(db, storage, me, scene_count=1)
    no_brand = page(db, me, "Trang chưa logo", page_id="777")
    theirs = page(db, teammate, "Trang của Bình", page_id="888")
    brand(db, teammate, "Kênh của Bình", fanpage=theirs)
    bare = page(db, me, "Trang logo trống", page_id="666")
    brand(db, me, "Kênh trống", fanpage=bare, logo=False)
    script_less = make_video(db, storage, me, scene_count=1)
    script_less.has_script = False
    db.commit()
    before = db.scalars(select(Video.id)).all()

    for arguments, message in (
        ({"video_id": 999999}, "Không tìm thấy video"),
        ({"video_id": script_less.id}, "chưa có kịch bản"),
        ({"video_id": source.id, "knowledge_topic_id": 999999}, "Không tìm thấy nhóm chủ đề"),
        ({"video_id": source.id, "fanpage_id": 999999}, "Không tìm thấy Fanpage"),
        ({"video_id": source.id, "fanpage_id": no_brand.id}, "chưa có logo"),
        ({"video_id": source.id, "fanpage_id": theirs.id}, "không có quyền dùng kênh"),
        ({"video_id": source.id, "fanpage_id": bare.id}, "Kênh chưa có logo"),
    ):
        refused = call(mcp_client, token, "duplicate_video", **arguments)
        assert refused["isError"] and message in str(refused), (arguments, refused)

    db.expire_all()
    assert db.scalars(select(Video.id)).all() == before


def test_a_rendered_copy_is_queued_on_the_members_page_and_filled_at_its_next_time(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    target = page(db, me, "Ăn Ngon Mỗi Ngày", page_id="999", times=["08:30", "11:30", "15:30", "18:00"])
    video = make_video(db, storage, me, scene_count=1)

    unrendered = call(mcp_client, token, "schedule_video", video_id=video.id, fanpage_id=target.id)
    assert unrendered["isError"] and "Video chưa có MP4" in str(unrendered)
    add_mp4(db, storage, video)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    scene.voice_text = "Lời mới sau khi render"
    db.commit()
    outdated = call(mcp_client, token, "schedule_video", video_id=video.id, fanpage_id=target.id)
    assert outdated["isError"] and "MP4 chưa cập nhật" in str(outdated)
    add_mp4(db, storage, video)

    queued = call(mcp_client, token, "schedule_video", video_id=video.id, fanpage_id=target.id)

    assert not queued.get("isError"), queued
    item = payload(queued)["item"]
    assert (item["fanpage_id"], item["video"]["id"], item["auto_comment"], item["added_by"]) == (
        target.id,
        video.id,
        True,
        me.name,
    )
    again = call(mcp_client, token, "schedule_video", video_id=video.id, fanpage_id=target.id)
    assert again["isError"] and "đã ở trong một hàng chờ" in str(again)

    assert page_queue.fill(db, now()) == 1
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    assert post.fanpage_id == target.id and post.created_by_id == me.id
    assert post.scheduled_at - now() >= page_queue.FILL_LEAD - timedelta(seconds=1)
    assert post.scheduled_at.astimezone(page_queue.VIETNAM).strftime("%H:%M") in target.post_times
    assert db.scalar(select(PageQueueItem.id)) is None


def test_queueing_keeps_the_page_owner_rule_and_needs_the_write_scope(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    teammate = make_user(db, email="binh@doi.vn", name="Trần Bình")
    theirs = page(db, teammate, "Trang của Bình", page_id="888")
    video = make_video(db, storage, me, scene_count=1)
    add_mp4(db, storage, video)

    refused = call(mcp_client, token, "schedule_video", video_id=video.id, fanpage_id=theirs.id)
    assert refused["isError"] and "Chỉ chủ Page" in str(refused)

    row = db.scalar(select(McpConnection))
    row.scopes = "reels:read"
    db.commit()
    read_only = call(mcp_client, token, "schedule_video", video_id=video.id)
    assert read_only["isError"] and "chỉ có quyền đọc" in str(read_only)
    assert call(mcp_client, token, "duplicate_video", video_id=video.id)["isError"]
    assert db.scalar(select(PageQueueItem.id)) is None
