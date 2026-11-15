"""MCP read tools for running the team's flow from an assistant: a member's Pages and queues, how posts did, the job
log and visitors' comments; each reads what the web's own pages read, and never a token."""

from datetime import timedelta

from conftest import make_user, make_video
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)
from test_page_queue import page

from reels_api.models import Brand, Job, PageComment, PageQueueItem, PostMetrics, Publication
from reels_api.sessions import now


def posted(db, storage, user, fanpage, views, days_ago=3, title_count=1):
    video = make_video(db, storage, user, scene_count=title_count)
    live = now() - timedelta(days=days_ago)
    post = Publication(
        video_id=video.id,
        platform="facebook",
        created_by_id=user.id,
        fanpage_id=fanpage.id,
        remote_id=f"r{video.id}",
        status="published",
        published_at=live,
    )
    db.add(post)
    db.flush()
    for window in ("48h", "latest"):
        db.add(PostMetrics(publication_id=post.id, window=window, views=views, shares=views // 10, measured_at=live))
    db.commit()
    return post


def test_the_members_pages_show_their_times_logo_queue_and_schedule(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    teammate = make_user(db, email="binh@doi.vn", name="Trần Bình")
    mine = page(db, me, "Ăn Ngon Mỗi Ngày", page_id="999", times=["08:30", "18:00"])
    page(db, teammate, "Trang của Bình", page_id="888")
    db.add(Brand(name="Ăn Ngon", slug="an-ngon", owner_id=me.id, fanpage_id=mine.id, logo_badge_path="b.png"))
    waiting = make_video(db, storage, me, scene_count=1)
    db.add(PageQueueItem(fanpage_id=mine.id, video_id=waiting.id, position=1, added_by_id=me.id, error="Lỗi thử"))
    booked = make_video(db, storage, me, scene_count=1)
    at = now() + timedelta(days=1)
    db.add(
        Publication(
            video_id=booked.id,
            platform="facebook",
            created_by_id=me.id,
            fanpage_id=mine.id,
            status="scheduled",
            scheduled_at=at,
        )
    )
    db.commit()

    answer = call(mcp_client, tokens["access_token"], "list_my_pages")

    assert not answer.get("isError"), answer
    (row,) = payload(answer)["pages"]
    assert (row["id"], row["name"], row["post_times"], row["own_times"]) == (
        mine.id,
        "Ăn Ngon Mỗi Ngày",
        ["08:30", "18:00"],
        True,
    )
    assert row["logo"]["has_logo"] is True and row["logo"]["on"] is True
    assert row["queue"] == [
        {
            "item_id": row["queue"][0]["item_id"],
            "video_id": waiting.id,
            "title": row["queue"][0]["title"],
            "error": "Lỗi thử",
        }
    ]
    assert [(post["video_id"], post["status"]) for post in row["scheduled"]] == [(booked.id, "scheduled")]
    assert "token" not in str(answer).lower()

    everyone = payload(call(mcp_client, tokens["access_token"], "list_my_pages", mine_only=False))
    assert {page_row["name"] for page_row in everyone["pages"]} == {"Ăn Ngon Mỗi Ngày", "Trang của Bình"}


def test_post_stats_rank_the_pages_published_posts_by_views(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    teammate = make_user(db, email="binh@doi.vn", name="Trần Bình")
    mine = page(db, me, "Ăn Ngon Sống Khỏe", page_id="999")
    theirs = page(db, teammate, "Trang của Bình", page_id="888")
    low = posted(db, storage, me, mine, 300)
    high = posted(db, storage, me, mine, 9000)
    posted(db, storage, me, mine, 50000, days_ago=60)  # older than the window
    other = posted(db, storage, teammate, theirs, 20000)

    ranked = payload(call(mcp_client, token, "list_post_stats", fanpage_id=mine.id))

    assert [row["post_id"] for row in ranked["posts"]] == [high.id, low.id] and ranked["total"] == 2
    top = ranked["posts"][0]
    assert (top["video_id"], top["views"], top["views_48h"], top["shares"], top["fanpage"]) == (
        high.video_id,
        9000,
        9000,
        900,
        "Ăn Ngon Sống Khỏe",
    )
    everyone = payload(call(mcp_client, token, "list_post_stats", limit=1))
    assert [row["post_id"] for row in everyone["posts"]] == [other.id]
    only_mine = payload(call(mcp_client, token, "list_post_stats", mine=True))
    assert other.id not in [row["post_id"] for row in only_mine["posts"]]
    newest = payload(call(mcp_client, token, "list_post_stats", days=90, sort="newest", fanpage_id=mine.id))
    assert len(newest["posts"]) == 3
    assert call(mcp_client, token, "list_post_stats", fanpage_id=999999)["isError"]


def test_the_job_log_is_filtered_by_status_and_video(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    teammate = make_user(db, email="binh@doi.vn", name="Trần Bình")
    video = make_video(db, storage, me, scene_count=1)
    other = make_video(db, storage, me, scene_count=1)
    failed = Job(video_id=video.id, kind="render", status="failed", error="FFmpeg lỗi", created_by_id=me.id)
    db.add_all(
        [
            failed,
            Job(video_id=other.id, kind="render", status="queued", created_by_id=me.id),
            Job(video_id=video.id, kind="script", status="done", created_by_id=teammate.id),
        ]
    )
    db.commit()

    mine = payload(call(mcp_client, token, "list_jobs"))
    assert {row["status"] for row in mine["jobs"]} == {"failed", "queued"}
    broken = payload(call(mcp_client, token, "list_jobs", status="failed"))["jobs"]
    assert [(row["id"], row["error"], row["video_id"]) for row in broken] == [(failed.id, "FFmpeg lỗi", video.id)]
    of_video = payload(call(mcp_client, token, "list_jobs", mine=False, video_id=video.id))["jobs"]
    assert {row["status"] for row in of_video} == {"failed", "done"}


def test_visitors_comments_are_read_but_never_answered(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    mine = page(db, me, "Ăn Ngon Mỗi Ngày", page_id="999")
    post = posted(db, storage, me, mine, 100)
    db.add_all(
        [
            PageComment(
                publication_id=post.id,
                remote_id="c1",
                author_name="Chị Lan",
                message="Món này nấu bao lâu?",
                created_at=now() - timedelta(hours=1),
            ),
            PageComment(
                publication_id=post.id,
                remote_id="c2",
                author_name="Anh Tú",
                message="Hay quá",
                created_at=now() - timedelta(hours=2),
                answered=True,
            ),
        ]
    )
    db.commit()

    open_ones = payload(call(mcp_client, token, "list_comments"))

    assert [(row["author"], row["message"]) for row in open_ones["comments"]] == [("Chị Lan", "Món này nấu bao lâu?")]
    assert open_ones["comments"][0]["post"]["fanpage"] == "Ăn Ngon Mỗi Ngày"
    assert len(payload(call(mcp_client, token, "list_comments", state="all"))["comments"]) == 2


def test_the_read_tools_are_read_only(mcp_client, db, storage):  # noqa: F811
    from test_mcp import rpc

    _, _, tokens, _ = grant(mcp_client, db)
    tools = {
        tool["name"]: tool for tool in rpc(mcp_client, tokens["access_token"], "tools/list").json()["result"]["tools"]
    }
    for name in ("list_my_pages", "list_post_stats", "list_jobs", "list_comments"):
        assert tools[name]["annotations"]["readOnlyHint"] is True, name
