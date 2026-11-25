"""MCP tools for articles ("Bài viết"): create, read, edit, photos, text card, post or schedule, unschedule, list,
delete. They are the web's own routes; posting needs the `reels:publish` scope, which the consent screen names
(decisions 2026-11-24)."""

from datetime import UTC, datetime, timedelta

from conftest import first_topic
from sqlalchemy import select
from test_article_posts import page_id
from test_mcp import authorize, call, grant, mcp_client, payload, register, rpc, ticket_of  # noqa: F401

from reels_api.models import Article, Job, McpConnection, Publication


def tomorrow() -> str:
    return (datetime.now(UTC) + timedelta(days=1)).isoformat()


def allow_publish(db) -> None:
    row = db.scalar(select(McpConnection))
    row.scopes = "reels:read reels:write reels:publish"
    db.commit()


def draft(client, token, db, caption="Ngủ đủ giấc giúp tim khoẻ.\n\nTối nay thử đi ngủ sớm 30 phút nhé."):
    made = call(
        client, token, "create_article", knowledge_topic_id=first_topic(db).id, caption=caption, hashtags=["#suckhoe"]
    )
    assert not made.get("isError"), made
    return payload(made)


def test_the_consent_screen_names_the_posting_scope(mcp_client, db):  # noqa: F811
    from conftest import login, make_user

    make_user(db)
    login(mcp_client)
    cid = register(mcp_client).json()["client_id"]
    plain = authorize(mcp_client, cid)
    assert "Quyền đăng bài lên Page" not in plain.text and "không được đăng bài" in plain.text
    ticket_of(plain)
    asked = authorize(mcp_client, cid, scope="reels:read reels:write reels:publish")
    assert "Quyền đăng bài lên Page" in asked.text and "không được đăng bài" not in asked.text


def test_an_article_is_made_edited_photographed_and_listed(mcp_client, db):  # noqa: F811
    _, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    made = draft(mcp_client, token, db)
    assert (made["status"], made["hashtags"], made["images"]) == ("draft", ["#suckhoe"], [])
    assert made["editor_url"].endswith(f"/articles/{made['id']}")

    edited = call(mcp_client, token, "update_article", article_id=made["id"], hashtags=["#a", "#b"], kind="meo")
    assert payload(edited)["hashtags"] == ["#a", "#b"] and payload(edited)["kind"] == "meo"
    too_many = call(mcp_client, token, "update_article", article_id=made["id"], hashtags=[f"#t{n}" for n in range(6)])
    assert too_many["isError"]

    card = payload(call(mcp_client, token, "add_article_text_card", article_id=made["id"], preset="kem"))
    assert [image["source"] for image in card["images"]] == ["text_card"]
    called = call(mcp_client, token, "add_article_composite", article_id=made["id"])
    assert called["isError"]  # no source photo named
    neither = call(mcp_client, token, "add_article_image", article_id=made["id"])
    assert neither["isError"]

    read = payload(call(mcp_client, token, "get_article", article_id=made["id"]))
    assert read["id"] == made["id"] and len(read["images"]) == 1
    listed = payload(call(mcp_client, token, "list_articles"))
    assert [row["id"] for row in listed["articles"]] == [made["id"]] and listed["total"] == 1
    assert {kind["value"] for kind in listed["kinds"]} >= {"kien_thuc", "meo"}

    assert not call(mcp_client, token, "delete_article", article_id=made["id"]).get("isError")
    assert db.get(Article, made["id"]) is None


def test_posting_needs_the_publish_scope(mcp_client, db):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    made = draft(mcp_client, token, db)
    pid = page_id(db, me)
    refused = call(mcp_client, token, "publish_article", article_id=made["id"], fanpage_id=pid)
    assert refused["isError"] and "quyền đăng bài" in refused["content"][0]["text"]
    assert db.scalar(select(Job).where(Job.article_id == made["id"])) is None
    assert db.scalar(select(Publication).where(Publication.article_id == made["id"])) is None


def test_a_post_is_scheduled_and_then_unscheduled(mcp_client, db):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    allow_publish(db)
    made = draft(mcp_client, token, db)
    pid = page_id(db, me)

    soon = call(
        mcp_client,
        token,
        "publish_article",
        article_id=made["id"],
        fanpage_id=pid,
        scheduled_at="2020-01-01T00:00:00+07:00",
    )
    assert soon["isError"]
    naive = call(
        mcp_client, token, "publish_article", article_id=made["id"], fanpage_id=pid, scheduled_at="2030-01-01T00:00:00"
    )
    assert naive["isError"]

    posted = call(mcp_client, token, "publish_article", article_id=made["id"], fanpage_id=pid, scheduled_at=tomorrow())
    assert not posted.get("isError"), posted
    saved = payload(posted)
    assert (saved["status"], saved["posts"][0]["status"], saved["posts"][0]["fanpage_id"]) == (
        "publishing",
        "pending",
        pid,
    )
    job = db.scalar(select(Job).where(Job.article_id == made["id"]))
    assert (job.kind, job.status) == ("publish", "queued")
    again = call(mcp_client, token, "publish_article", article_id=made["id"], fanpage_id=pid)
    assert again["isError"]  # busy: a job is waiting

    gone = call(mcp_client, token, "unschedule_article", article_id=made["id"])
    assert not gone.get("isError"), gone
    db.refresh(job)
    assert job.status == "cancelled"
    assert payload(gone)["posts"][0]["status"] == "cancelled" and payload(gone)["status"] == "draft"
    nothing = call(mcp_client, token, "unschedule_article", article_id=made["id"])
    assert nothing["isError"]


def test_another_members_page_and_a_posted_article_are_refused(mcp_client, db):  # noqa: F811
    from conftest import make_user

    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    allow_publish(db)
    made = draft(mcp_client, token, db)
    other = make_user(db, email="khac@example.com", name="Người khác")
    theirs = page_id(db, other, page="777", name="Page của người khác")
    assert call(mcp_client, token, "publish_article", article_id=made["id"], fanpage_id=theirs)["isError"]
    pid = page_id(db, me, page="778", name="Page của tôi")
    assert not call(mcp_client, token, "publish_article", article_id=made["id"], fanpage_id=pid).get("isError")
    assert call(mcp_client, token, "delete_article", article_id=made["id"])["isError"]
