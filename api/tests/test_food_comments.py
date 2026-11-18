"""A detailed comment per dish, written by the member's assistant over MCP and written under the post by the worker."""

from datetime import UTC, datetime, timedelta

from conftest import first_topic, make_user, make_video
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)

from reels_api.models import Publication

GOOD = "1. Rau muống luộc. Công dụng: cung cấp chất xơ, giúp no lâu. Cách làm: luộc 2 phút rồi vớt ra. Ai không nên ăn: người đang dùng thuốc cần hỏi bác sĩ."


def post_for(db, video, hours_ago=1, **fields):
    post = Publication(
        video_id=video.id,
        created_by_id=video.created_by_id,
        platform="facebook",
        status="published",
        remote_id="reel-1",
        published_at=datetime.now(UTC) - timedelta(hours=hours_ago),
        **fields,
    )
    db.add(post)
    db.commit()
    return post


def test_only_my_videos_live_within_the_week_are_listed_with_their_scenes(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    recent, old, never = (make_video(db, storage, me, scene_count=2) for _ in range(3))
    other = make_video(db, storage, make_user(db, email="b@doi.vn", name="B"), scene_count=1)
    post_for(db, recent)
    post_for(db, old, hours_ago=24 * 8)
    post_for(db, other)
    listed = payload(call(mcp_client, token, "list_videos_for_food_comments"))["videos"]
    assert [row["video_id"] for row in listed] == [recent.id]
    assert len(listed[0]["scenes"]) == 2 and listed[0]["comments_saved"] == 0 and never.id not in str(listed)


def test_saving_stores_one_comment_per_dish_and_asks_the_worker_for_each_live_post(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, me, scene_count=2)
    post = post_for(db, video)
    saved = call(mcp_client, token, "set_food_comments", video_id=video.id, comments=[GOOD, GOOD.replace("1.", "2.")])
    assert not saved.get("isError"), saved
    assert payload(saved)["saved"] == 2 and payload(saved)["posts_asked"] == 1
    db.refresh(video)
    db.refresh(post)
    assert len(video.extra_comments) == 2 and post.comment_requested_at is not None


def test_a_cure_promise_a_banned_word_or_a_short_comment_is_refused(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, me, scene_count=1)
    post_for(db, video)
    topic = first_topic(db)
    topic.banned_words = ["thần dược"]
    db.commit()
    for bad in (GOOD + " Ăn là chữa khỏi bệnh.", GOOD + " Đúng là thần dược.", "Ngắn quá"):
        refused = call(mcp_client, token, "set_food_comments", video_id=video.id, comments=[bad])
        assert refused["isError"], bad
    assert db.get(type(video), video.id).extra_comments == []


def test_another_members_video_a_video_not_live_and_a_pasted_by_hand_video(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    theirs = make_video(db, storage, make_user(db, email="b@doi.vn", name="B"), scene_count=1)
    post_for(db, theirs)
    assert call(mcp_client, token, "set_food_comments", video_id=theirs.id, comments=[GOOD])["isError"]
    quiet = make_video(db, storage, me, scene_count=1)
    assert call(mcp_client, token, "set_food_comments", video_id=quiet.id, comments=[GOOD])["isError"]
    manual = make_video(db, storage, me, scene_count=1)
    manual.manual_comment = True
    post = post_for(db, manual)
    saved = payload(call(mcp_client, token, "set_food_comments", video_id=manual.id, comments=[GOOD]))
    db.refresh(post)
    assert saved["posts_asked"] == 0 and saved["note"] and post.comment_requested_at is None
    assert db.scalar(select(Publication.id).where(Publication.video_id == manual.id)) is not None
