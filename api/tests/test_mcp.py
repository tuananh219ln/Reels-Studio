"""Exercise the OAuth boundary and real MCP transport without any external AI calls."""

import base64
import hashlib
import json
import logging
from html import escape
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import WEB_ORIGIN, first_topic, login, make_user, make_video
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from reels_api.db import get_db
from reels_api.main import create_app
from reels_api.models import Job, Scene, Video
from reels_api.videos import assistant_writer

PUBLIC = WEB_ORIGIN + "/api/mcp"
CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"
VERIFIER = "a" * 43
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")


@pytest.fixture
def mcp_client(db, monkeypatch):
    monkeypatch.setenv("MCP_PUBLIC_URL", PUBLIC)
    monkeypatch.setenv("ALLOWED_ORIGINS", WEB_ORIGIN)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, base_url=WEB_ORIGIN, headers={"Origin": WEB_ORIGIN}) as client:
        yield client


def register(client, redirect=CALLBACK):
    return client.post(
        "/api/mcp/oauth/register",
        json={"redirect_uris": [redirect], "token_endpoint_auth_method": "none", "client_name": "ChatGPT"},
        headers={"Origin": "https://chatgpt.com"},
    )


def authorize(client, client_id, **extra):
    return client.get(
        "/api/mcp/oauth/authorize",
        follow_redirects=False,
        params={
            "client_id": client_id,
            "redirect_uri": CALLBACK,
            "response_type": "code",
            "code_challenge": CHALLENGE,
            "code_challenge_method": "S256",
            "scope": "reels:read reels:write",
            "resource": PUBLIC,
            "state": "client-state",
            **extra,
        },
    )


def ticket_of(response):
    """The consent screen is the authorize response itself; its form carries the ticket."""
    import re

    assert response.status_code == 200, response.text
    return re.search(r'name="ticket" value="([^"]+)"', response.text).group(1)


def callback_of(response):
    """Where the consent answer sends the browser. A page, never a 303: the web proxy in production (OpenNext on
    Cloudflare) follows redirects itself, so a 303 sent the member to Claude's 404 instead of to Claude."""
    import re
    from html import unescape

    assert response.status_code == 200, response.text
    assert "location" not in response.headers
    return unescape(re.search(r'http-equiv="refresh" content="0;url=([^"]+)"', response.text).group(1))


def grant(client, db):
    user = make_user(db)
    login(client)
    client_id = register(client).json()["client_id"]
    page = authorize(client, client_id)
    ticket = ticket_of(page)
    approved = client.post(
        "/api/mcp/oauth/consent", data={"ticket": ticket, "decision": "allow"}, follow_redirects=False
    )
    params = parse_qs(urlparse(callback_of(approved)).query)
    assert params["state"] == ["client-state"]
    assert params["iss"] == [PUBLIC + "/oauth"]
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": CALLBACK,
        "code": params["code"][0],
        "code_verifier": VERIFIER,
        "resource": PUBLIC,
    }
    tokens = client.post("/api/mcp/oauth/token", data=data, headers={"Origin": "https://chatgpt.com"})
    assert tokens.status_code == 200, tokens.text
    return user, client_id, tokens.json(), data


def rpc(client, token, method, params=None):
    return client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json, text/event-stream",
            "Origin": "https://chatgpt.com",
        },
    )


def call(client, token, name, **arguments):
    response = rpc(client, token, "tools/call", {"name": name, "arguments": arguments})
    assert response.status_code == 200, response.text
    return response.json()["result"]


def test_disabled_by_default(client):
    assert client.get("/.well-known/oauth-protected-resource/api/mcp").status_code == 404


def test_discovery_challenge_and_client_registration(mcp_client):
    response = mcp_client.post("/api/mcp", json={})
    assert response.status_code == 401
    assert (
        'resource_metadata="http://localhost:3000/.well-known/oauth-protected-resource/api/mcp"'
        in response.headers["www-authenticate"]
    )
    resource = mcp_client.get("/.well-known/oauth-protected-resource/api/mcp").json()
    assert resource["resource"] == PUBLIC
    assert resource["authorization_servers"] == [PUBLIC + "/oauth"]
    metadata = mcp_client.get("/.well-known/oauth-authorization-server/api/mcp/oauth").json()
    assert metadata["code_challenge_methods_supported"] == ["S256"]
    assert metadata["token_endpoint_auth_methods_supported"] == ["none"]
    assert register(mcp_client).status_code == 201
    assert register(mcp_client, "https://evil.example/callback").status_code == 400


def test_the_login_link_of_the_authorize_page_comes_back_to_the_same_request(mcp_client):
    import re
    from html import unescape

    cid = register(mcp_client).json()["client_id"]
    page = authorize(mcp_client, cid)
    assert page.status_code == 401
    link = re.search(r'<a href="(/login\?next=[^"]+)">Đăng nhập Reels Studio</a>', page.text)
    assert link, page.text
    back = parse_qs(urlparse(unescape(link.group(1))).query)["next"][0]
    assert back.startswith("/api/mcp/oauth/authorize?")
    assert parse_qs(urlparse(back).query)["client_id"] == [cid]
    assert parse_qs(urlparse(back).query)["state"] == ["client-state"]


def test_consent_requires_login_and_valid_pkce_resource_redirect(mcp_client, db):
    cid = register(mcp_client).json()["client_id"]
    assert authorize(mcp_client, cid).status_code == 401
    make_user(db)
    login(mcp_client)
    for extra in (
        {"code_challenge_method": "plain"},
        {"resource": "https://evil.example"},
        {"redirect_uri": "https://evil.example/callback"},
        {"scope": "admin"},
    ):
        assert authorize(mcp_client, cid, **extra).status_code == 400
    page = authorize(mcp_client, cid)
    ticket = ticket_of(page)
    denied = mcp_client.post(
        "/api/mcp/oauth/consent", data={"ticket": ticket, "decision": "deny"}, follow_redirects=False
    )
    assert parse_qs(urlparse(callback_of(denied)).query)["error"] == ["access_denied"]
    assert mcp_client.post("/api/mcp/oauth/consent", data={"ticket": ticket, "decision": "allow"}).status_code == 400


def test_token_is_one_use_refresh_rotates_and_revoke_disconnects(mcp_client, db):
    _, cid, tokens, exchanged = grant(mcp_client, db)
    assert tokens["token_type"] == "Bearer"
    assert mcp_client.post("/api/mcp/oauth/token", data=exchanged).status_code == 400
    refresh = {
        "grant_type": "refresh_token",
        "client_id": cid,
        "refresh_token": tokens["refresh_token"],
        "resource": PUBLIC,
    }
    renewed = mcp_client.post("/api/mcp/oauth/token", data=refresh)
    assert renewed.status_code == 200
    assert mcp_client.post("/api/mcp/oauth/token", data=refresh).status_code == 400
    assert rpc(mcp_client, tokens["access_token"], "tools/list").status_code == 401
    new_token = renewed.json()["access_token"]
    assert rpc(mcp_client, new_token, "tools/list").status_code == 200
    connections = mcp_client.get("/api/mcp/connections").json()
    assert len(connections) == 1
    assert "access_token" not in connections[0]
    assert mcp_client.delete(f"/api/mcp/connections/{connections[0]['id']}").status_code == 200
    assert rpc(mcp_client, new_token, "tools/list").status_code == 401


def refresh_with(client, cid, refresh_token):
    return client.post(
        "/api/mcp/oauth/token",
        data={"grant_type": "refresh_token", "client_id": cid, "refresh_token": refresh_token, "resource": PUBLIC},
    )


def test_a_new_connection_lasts_30_days_from_the_grant(mcp_client, db):
    from datetime import timedelta

    from reels_api.models import McpConnection
    from reels_api.sessions import now

    grant(mcp_client, db)
    row = db.scalar(select(McpConnection))
    assert abs(row.expires_at - (now() + timedelta(days=30))) < timedelta(minutes=1)


def test_a_refresh_pushes_the_connections_end_30_days_out_and_the_new_token_works(mcp_client, db):
    from datetime import timedelta

    from reels_api.models import McpConnection
    from reels_api.sessions import now

    _, cid, tokens, _ = grant(mcp_client, db)
    row = db.scalar(select(McpConnection))
    row.expires_at = now() + timedelta(days=1)
    db.commit()
    renewed = refresh_with(mcp_client, cid, tokens["refresh_token"])
    assert renewed.status_code == 200, renewed.text
    db.refresh(row)
    assert abs(row.expires_at - (now() + timedelta(days=30))) < timedelta(minutes=1)
    assert renewed.json()["expires_in"] > 3500
    assert rpc(mcp_client, renewed.json()["access_token"], "tools/list").status_code == 200


def test_an_expired_connection_is_not_revived_by_a_refresh(mcp_client, db):
    from datetime import timedelta

    from reels_api.models import McpConnection
    from reels_api.sessions import now

    _, cid, tokens, _ = grant(mcp_client, db)
    row = db.scalar(select(McpConnection))
    ended = now() - timedelta(seconds=1)
    row.expires_at = ended
    db.commit()
    assert refresh_with(mcp_client, cid, tokens["refresh_token"]).status_code == 400
    db.refresh(row)
    assert row.expires_at == ended


def test_a_connection_granted_before_sliding_expiry_is_extended_on_its_first_refresh(mcp_client, db):
    """Before 2026-11-09 a connection's end was fixed at grant + 30 days and a refresh never moved it: one granted
    almost 30 days ago, with minutes left, now gets 30 more days and a full hour's token instead of the minutes."""
    from datetime import timedelta

    from reels_api.models import McpConnection
    from reels_api.sessions import now

    _, cid, tokens, _ = grant(mcp_client, db)
    row = db.scalar(select(McpConnection))
    row.created_at = now() - timedelta(days=30) + timedelta(minutes=10)
    row.expires_at = row.created_at + timedelta(days=30)
    db.commit()
    renewed = refresh_with(mcp_client, cid, tokens["refresh_token"])
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["expires_in"] > 3500
    db.refresh(row)
    assert row.expires_at > now() + timedelta(days=29)
    again = refresh_with(mcp_client, cid, renewed.json()["refresh_token"])
    assert again.status_code == 200, again.text


def test_tools_reuse_validation_locks_and_queue_and_never_expose_secrets(mcp_client, db, storage):
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user)
    catalog = rpc(mcp_client, token, "tools/list").json()["result"]["tools"]
    tools = {tool["name"]: tool for tool in catalog}
    assert tools["list_videos"]["annotations"]["readOnlyHint"] is True
    assert tools["render_video"]["annotations"]["readOnlyHint"] is False
    assert "publish" not in tools and "delete_video" not in tools
    result = call(mcp_client, token, "get_video", video_id=video.id)
    assert not result.get("isError")
    assert "password_hash" not in str(result)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    edited = call(mcp_client, token, "update_scene", scene_id=scene.id, voice_text="Ăn đa dạng để bổ sung dinh dưỡng.")
    assert not edited.get("isError")
    db.refresh(scene)
    assert scene.voice_text == "Ăn đa dạng để bổ sung dinh dưỡng."
    bad = call(mcp_client, token, "update_video", video_id=video.id, caption="a" * 5001)
    assert bad["isError"]
    rendered = call(mcp_client, token, "render_video", video_id=video.id)
    assert not rendered.get("isError"), rendered
    jobs = db.scalars(select(Job).where(Job.video_id == video.id)).all()
    assert [(j.kind, j.status, j.created_by_id) for j in jobs] == [("render", "queued", user.id)]
    assert call(mcp_client, token, "update_scene", scene_id=scene.id, voice_text="Không được lưu")["isError"]
    assert call(mcp_client, token, "render_video", video_id=video.id)["isError"]
    assert len(db.scalars(select(Job).where(Job.video_id == video.id)).all()) == 1


def test_disconnect_on_logout_disabled_user_and_forced_password(mcp_client, db):
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    user.must_change_password = True
    db.commit()
    assert rpc(mcp_client, token, "tools/list").status_code == 401
    user.must_change_password, user.is_active = False, False
    db.commit()
    assert rpc(mcp_client, token, "tools/list").status_code == 401
    user.is_active = True
    db.commit()
    assert mcp_client.post("/api/auth/logout").status_code == 200
    assert rpc(mcp_client, token, "tools/list").status_code == 401


def test_oauth_errors_use_protocol_format_and_pkce_cannot_be_bypassed(mcp_client, db):
    make_user(db)
    login(mcp_client)
    cid = register(mcp_client).json()["client_id"]
    invalid = authorize(mcp_client, cid, code_challenge_method="plain")
    assert invalid.json()["error"] == "invalid_request"
    page = authorize(mcp_client, cid)
    ticket = ticket_of(page)
    approved = mcp_client.post(
        "/api/mcp/oauth/consent", data={"ticket": ticket, "decision": "allow"}, follow_redirects=False
    )
    code = parse_qs(urlparse(callback_of(approved)).query)["code"][0]
    data = {
        "grant_type": "authorization_code",
        "client_id": cid,
        "redirect_uri": CALLBACK,
        "code": code,
        "code_verifier": "b" * 43,
        "resource": PUBLIC,
    }
    wrong = mcp_client.post("/api/mcp/oauth/token", data=data)
    assert wrong.status_code == 400
    assert wrong.json()["error"] == "invalid_grant"
    assert "no-store" in wrong.headers["cache-control"]
    assert mcp_client.post("/api/mcp/oauth/token", data={**data, "code_verifier": VERIFIER}).status_code == 200


def test_tokens_are_resource_bound_and_never_stored_in_plaintext(mcp_client, db, monkeypatch):
    from reels_api.models import McpConnection

    _, cid, tokens, _ = grant(mcp_client, db)
    row = db.scalar(select(McpConnection))
    assert tokens["access_token"] != row.access_hash
    assert tokens["refresh_token"] != row.refresh_hash
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://other.example/api/mcp")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://other.example")
    assert rpc(mcp_client, tokens["access_token"], "tools/list").status_code == 401
    refresh = mcp_client.post(
        "/api/mcp/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": cid,
            "refresh_token": tokens["refresh_token"],
            "resource": "https://other.example/api/mcp",
        },
    )
    assert refresh.status_code == 400


def test_cookie_and_bearer_permissions_are_separate_and_consent_checks_origin(mcp_client, db):
    _, _, tokens, _ = grant(mcp_client, db)
    cid = register(mcp_client).json()["client_id"]
    page = authorize(mcp_client, cid)
    ticket = ticket_of(page)
    assert (
        mcp_client.post(
            "/api/mcp/oauth/consent",
            data={"ticket": ticket, "decision": "allow"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert mcp_client.post("/api/mcp", json={}).status_code == 401  # a cookie is not MCP authority
    mcp_client.cookies.clear()
    assert (
        mcp_client.get("/api/videos", headers={"Authorization": "Bearer " + tokens["access_token"]}).status_code == 401
    )


def test_read_only_connection_cannot_edit_and_create_is_queued(mcp_client, db, storage):
    from conftest import first_topic

    from reels_api.models import McpConnection, Video

    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    groups = call(mcp_client, token, "list_topic_groups")
    assert not groups.get("isError")
    topic = first_topic(db)
    made = call(mcp_client, token, "create_video", topic="Rau xanh", knowledge_topic_id=topic.id)
    assert not made.get("isError"), made
    video = db.scalar(select(Video).where(Video.topic == "Rau xanh"))
    assert video is not None
    job = db.scalar(select(Job).where(Job.video_id == video.id))
    assert (job.kind, job.status, job.created_by_id) == ("script", "queued", user.id)
    listed = call(mcp_client, token, "list_videos", query="Rau", limit=1)
    assert not listed.get("isError")
    row = db.scalar(select(McpConnection))
    row.scopes = "reels:read"
    db.commit()
    assert not call(mcp_client, token, "get_video", video_id=video.id).get("isError")
    assert call(mcp_client, token, "update_video", video_id=video.id, caption="Không được lưu")["isError"]
    assert video.caption != "Không được lưu"


def test_expired_grants_and_missing_scene_images_never_queue_render(mcp_client, db, storage):
    from datetime import timedelta

    from reels_api.models import McpConnection
    from reels_api.sessions import now

    user, cid, tokens, _ = grant(mcp_client, db)
    video = make_video(db, storage, user, images=False)
    assert call(mcp_client, tokens["access_token"], "render_video", video_id=video.id)["isError"]
    assert db.scalar(select(Job.id).where(Job.video_id == video.id)) is None
    row = db.scalar(select(McpConnection))
    row.access_expires_at = now() - timedelta(seconds=1)
    db.commit()
    assert rpc(mcp_client, tokens["access_token"], "tools/list").status_code == 401
    row.expires_at = now() - timedelta(seconds=1)
    db.commit()
    assert (
        mcp_client.post(
            "/api/mcp/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": cid,
                "refresh_token": tokens["refresh_token"],
                "resource": PUBLIC,
            },
        ).status_code
        == 400
    )


def test_consent_is_shown_by_the_authorize_request_and_is_visible_only_to_its_member_session(mcp_client, db):
    make_user(db)
    login(mcp_client)
    cid = register(mcp_client).json()["client_id"]
    response = authorize(mcp_client, cid)
    # The consent screen itself, not a hop to the web app that could lose the ticket on the way.
    assert response.status_code == 200
    assert "Cho phép ChatGPT kết nối?" in response.text and "an@doi.vn" in response.text
    assert "<code>chatgpt.com</code>" in response.text and 'value="allow"' in response.text
    assert "form-action 'self' https://chatgpt.com" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "same-origin"
    ticket = ticket_of(response)
    details = mcp_client.get(f"/api/mcp/authorizations/{ticket}")
    assert details.status_code == 200
    assert details.json()["scopes"] == ["reels:read", "reels:write"]
    assert details.json()["email"] == "an@doi.vn"
    mcp_client.cookies.clear()
    assert mcp_client.get(f"/api/mcp/authorizations/{ticket}").status_code == 401


def test_member_cannot_view_or_revoke_another_members_connection(mcp_client, db):
    grant(mcp_client, db)
    connection_id = mcp_client.get("/api/mcp/connections").json()[0]["id"]
    make_user(db, email="binh@doi.vn", name="Bình")
    login(mcp_client, email="binh@doi.vn")
    assert mcp_client.get("/api/mcp/connections").json() == []
    refused = mcp_client.delete(f"/api/mcp/connections/{connection_id}")
    assert refused.status_code == 400
    login(mcp_client)
    assert mcp_client.get("/api/mcp/connections").json()[0]["id"] == connection_id


def test_mcp_initialization_is_stateless_and_reports_protocol_capabilities(mcp_client, db):
    _, _, tokens, _ = grant(mcp_client, db)
    response = rpc(
        mcp_client,
        tokens["access_token"],
        "initialize",
        {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "reels-tests", "version": "1"},
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "Reels Studio"
    assert "tools" in response.json()["result"]["capabilities"]
    assert "mcp-session-id" not in response.headers


def test_slow_tool_database_acquisition_does_not_stall_other_http_requests(mcp_client, db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    _, _, tokens, _ = grant(mcp_client, db)
    entered, release = Event(), Event()
    calls = 0

    def acquire_database():
        nonlocal calls
        calls += 1
        # The verifier acquires first; the tool's second acquisition represents a busy DB pool.
        if calls == 2:
            entered.set()
            assert release.wait(5), "tool database acquisition was never released"
        return db

    mcp_client.app.dependency_overrides[get_db] = acquire_database
    with ThreadPoolExecutor(max_workers=2) as executor:
        request = executor.submit(call, mcp_client, tokens["access_token"], "list_topic_groups")
        assert entered.wait(3)
        try:
            discovery = executor.submit(mcp_client.get, "/.well-known/oauth-protected-resource/api/mcp")
            assert discovery.result(timeout=1).status_code == 200
        finally:
            release.set()
        assert not request.result().get("isError")


# Claude: the hosted apps' callback, and Claude Code's loopback one on a port that changes every session.
CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"


def grant_to(client, db, registered, asked):
    """A grant whose client registered `registered` and whose authorization asks to go back to `asked`."""
    make_user(db)
    login(client)
    made = register(client, registered)
    assert made.status_code == 201, made.text
    cid = made.json()["client_id"]
    ticket = ticket_of(authorize(client, cid, redirect_uri=asked))
    details = client.get(f"/api/mcp/authorizations/{ticket}").json()
    approved = client.post(
        "/api/mcp/oauth/consent", data={"ticket": ticket, "decision": "allow"}, follow_redirects=False
    )
    assert callback_of(approved).startswith(asked + "?")
    code = parse_qs(urlparse(callback_of(approved)).query)["code"][0]
    return cid, details, code


def payload(result: dict) -> dict:
    """A tool's dict result, as the JSON text of its first content block."""
    return json.loads(result["content"][0]["text"])


def exchange(client, cid, code, redirect):
    data = {
        "grant_type": "authorization_code",
        "client_id": cid,
        "redirect_uri": redirect,
        "code": code,
        "code_verifier": VERIFIER,
        "resource": PUBLIC,
    }
    return client.post("/api/mcp/oauth/token", data=data)


def test_claude_connects_through_its_hosted_callback_and_is_named_on_consent(mcp_client, db):
    cid, details, code = grant_to(mcp_client, db, CLAUDE_CALLBACK, CLAUDE_CALLBACK)
    assert details["app"] == "Claude"
    assert details["redirect_host"] == "claude.ai" and details["loopback"] is False
    tokens = exchange(mcp_client, cid, code, CLAUDE_CALLBACK)
    assert tokens.status_code == 200, tokens.text
    assert rpc(mcp_client, tokens.json()["access_token"], "tools/list").status_code == 200
    assert [row["app"] for row in mcp_client.get("/api/mcp/connections").json()] == ["Claude"]
    assert register(mcp_client, "https://claude.com/api/mcp/auth_callback").status_code == 201


def test_claude_code_loopback_matches_any_port_but_the_exchange_needs_the_one_used(mcp_client, db):
    cid, details, code = grant_to(mcp_client, db, "http://localhost:3118/callback", "http://localhost:40123/callback")
    assert details["app"] == "Claude Code" and details["loopback"] is True
    assert details["redirect_host"] == "localhost:40123"
    assert exchange(mcp_client, cid, code, "http://localhost:3118/callback").status_code == 400
    tokens = exchange(mcp_client, cid, code, "http://localhost:40123/callback")
    assert tokens.status_code == 200, tokens.text
    # Another loopback host, path or scheme is not the one registered.
    for other in (
        "http://127.0.0.1:40123/callback",
        "http://localhost:40123/other",
        "https://localhost:40123/callback",
    ):
        assert authorize(mcp_client, cid, redirect_uri=other).status_code == 400


# Muse (Meta's assistant): the exact callback it sent, read from the "MCP registration refused" log line.
MUSE_CALLBACK = "https://agent.meta.ai/api/hatch/oauth/callback"


def test_muse_registers_with_its_hosted_callback(mcp_client):
    made = mcp_client.post(
        "/api/mcp/oauth/register",
        json={"redirect_uris": [MUSE_CALLBACK], "token_endpoint_auth_method": "none", "client_name": "Muse"},
    )
    assert made.status_code == 201, made.text
    assert made.json()["client_name"] == "Muse"
    # Only that exact URI: nothing else on Meta's host, nor a look-alike host.
    for other in (
        "https://agent.meta.ai/api/hatch/oauth/other",
        "https://agent.meta.ai/api/hatch/oauth/callback/",
        "http://agent.meta.ai/api/hatch/oauth/callback",
        "https://meta.ai/api/hatch/oauth/callback",
        "https://agent.meta.ai.evil.example/api/hatch/oauth/callback",
    ):
        refused = register(mcp_client, other)
        assert refused.status_code == 400 and refused.json()["error"] == "invalid_client_metadata"


def test_muse_connects_with_read_and_write_and_edits_a_video(mcp_client, db, storage):
    user = make_user(db)
    login(mcp_client)
    cid = register(mcp_client, MUSE_CALLBACK).json()["client_id"]
    consent = authorize(mcp_client, cid, redirect_uri=MUSE_CALLBACK, scope="reels:read reels:write")
    ticket = ticket_of(consent)
    assert "Cho phép Muse kết nối?" in consent.text
    assert "Quyền sửa và tạo công việc" in consent.text
    assert "Kết nối với một chương trình trên máy tính" not in consent.text
    details = mcp_client.get(f"/api/mcp/authorizations/{ticket}").json()
    assert details["app"] == "Muse" and details["loopback"] is False
    assert details["redirect_host"] == "agent.meta.ai"
    approved = mcp_client.post(
        "/api/mcp/oauth/consent", data={"ticket": ticket, "decision": "allow"}, follow_redirects=False
    )
    assert callback_of(approved).startswith(MUSE_CALLBACK + "?")
    code = parse_qs(urlparse(callback_of(approved)).query)["code"][0]
    tokens = exchange(mcp_client, cid, code, MUSE_CALLBACK)
    assert tokens.status_code == 200, tokens.text
    [connection] = mcp_client.get("/api/mcp/connections").json()
    assert connection["app"] == "Muse"
    assert set(connection["scopes"].split()) == {"reels:read", "reels:write"}
    video = make_video(db, storage, user)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    edited = call(mcp_client, tokens.json()["access_token"], "update_scene", scene_id=scene.id, voice_text="Muse sửa.")
    assert not edited.get("isError"), edited
    db.refresh(scene)
    assert scene.voice_text == "Muse sửa."

    # A video Muse writes says so: on its page and on every list, never "Claude".
    made = call(
        mcp_client,
        tokens.json()["access_token"],
        "create_video_from_script",
        topic="Muse viết",
        knowledge_topic_id=video.knowledge_topic_id,
        script="Cảnh một\nĐọc: Lời một.",
    )
    assert not made.get("isError"), made
    written = db.scalar(select(Video).where(Video.topic == "Muse viết"))
    assert written.assistant_app == "Muse"
    assert payload(made)["script_by"].startswith("Muse của thành viên qua kết nối MCP")
    row = next(row for row in mcp_client.get("/api/videos").json() if row["id"] == written.id)
    assert (row["made_via"], row["assistant_app"]) == ("assistant", "Muse")


def test_the_hosted_apps_and_claude_code_keep_their_names(mcp_client, db):
    assert register(mcp_client).json()["client_name"] == "ChatGPT"
    assert register(mcp_client, CLAUDE_CALLBACK).json()["client_name"] == "Claude"
    make_user(db)
    login(mcp_client)
    cid = register(mcp_client, "http://localhost:3118/callback").json()["client_id"]
    consent = authorize(mcp_client, cid, redirect_uri="http://localhost:3118/callback")
    assert "Cho phép Claude Code kết nối?" in consent.text
    assert "Kết nối với một chương trình trên máy tính" in consent.text


@pytest.mark.parametrize(
    "redirect",
    [
        "http://localhost.evil.example/callback",
        "http://evil.example:3118/callback",
        "http://localhost:99999/callback",
        "http://user@localhost:3118/callback",
        "https://claude.ai/api/mcp/other",
        "https://claude.ai.evil.example/api/mcp/auth_callback",
    ],
)
def test_only_the_ai_apps_callbacks_can_register(mcp_client, redirect):
    assert register(mcp_client, redirect).status_code == 400


def test_a_client_may_register_several_allowed_callbacks_but_never_an_unknown_one(mcp_client):
    both = ["http://localhost/callback", "http://127.0.0.1/callback"]
    made = mcp_client.post(
        "/api/mcp/oauth/register", json={"redirect_uris": both, "token_endpoint_auth_method": "none"}
    )
    assert made.status_code == 201, made.text
    assert made.json()["redirect_uris"] == both
    mixed = [CLAUDE_CALLBACK, "https://evil.example/callback"]
    refused = mcp_client.post(
        "/api/mcp/oauth/register", json={"redirect_uris": mixed, "token_endpoint_auth_method": "none"}
    )
    assert refused.status_code == 400


def test_a_refused_registration_is_logged_with_what_the_client_sent(mcp_client, caplog):
    # A new assistant (Muse) is added to the allowlist only with the exact callback it sends, read from this line.
    # WARNING, not INFO: the api runs plain uvicorn, which only prints its own loggers' INFO lines.
    caplog.set_level(logging.WARNING, logger="reels_api.routes_mcp")
    refused = mcp_client.post(
        "/api/mcp/oauth/register",
        json={
            "redirect_uris": ["https://evil.example.com/callback", CLAUDE_CALLBACK],
            "token_endpoint_auth_method": "none",
            "client_name": "Muse\nforged line",
        },
    )
    assert refused.status_code == 400
    assert refused.json()["error"] == "invalid_client_metadata"
    [line] = [r for r in caplog.records if r.name == "reels_api.routes_mcp"]
    assert line.levelno == logging.WARNING
    text = line.getMessage()
    assert "https://evil.example.com/callback" in text and CLAUDE_CALLBACK in text
    assert "Muse" in text and "\n" not in text
    # Refused for another reason than the callback: the line says what was sent, to tell the two apart.
    caplog.clear()
    other = mcp_client.post(
        "/api/mcp/oauth/register",
        json={"redirect_uris": [CALLBACK], "token_endpoint_auth_method": "client_secret_basic"},
    )
    assert other.status_code == 400
    assert "client_secret_basic" in caplog.text and CALLBACK in caplog.text


def test_an_accepted_registration_is_not_logged(mcp_client, caplog):
    caplog.set_level(logging.DEBUG, logger="reels_api.routes_mcp")
    assert register(mcp_client).status_code == 201
    assert not [r for r in caplog.records if r.name == "reels_api.routes_mcp"]


def test_an_unknown_client_at_authorize_is_logged(mcp_client, caplog):
    # A client that skips registration (a client id it made itself, or a metadata document URL) never reaches
    # register(): its id and callback are logged here instead.
    caplog.set_level(logging.WARNING, logger="reels_api.routes_mcp")
    response = authorize(
        mcp_client, "https://assistant.example/client.json", redirect_uri="https://assistant.example/cb"
    )
    assert response.status_code == 400
    assert "https://assistant.example/client.json" in caplog.text and "https://assistant.example/cb" in caplog.text


def test_a_product_video_is_made_from_a_hand_written_script_without_an_ai_job(mcp_client, db, storage):
    from conftest import first_topic

    from reels_api.models import Video

    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    script = "Nồi chiên không dầu 5 lít\nĐọc: Bếp nhỏ vẫn chiên giòn.\n\nChỉ 899 nghìn\nĐọc: Giá chỉ 899 nghìn."
    made = call(
        mcp_client,
        token,
        "create_video_from_script",
        topic="Nồi chiên 5L",
        knowledge_topic_id=first_topic(db).id,
        script=script,
    )
    assert not made.get("isError"), made
    video = db.scalar(select(Video).where(Video.topic == "Nồi chiên 5L"))
    assert video.hand_written and video.has_script and video.created_by_id == user.id
    assert video.written_via == "assistant"
    # The default test connection is ChatGPT's: the video names it, not "Claude".
    assert payload(made)["script_by"] == assistant_writer("ChatGPT")
    assert video.assistant_app == "ChatGPT"
    assert db.scalar(select(Job.id).where(Job.video_id == video.id)) is None
    scenes = db.scalars(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position)
    ).all()
    assert [(s.text, s.voice_text) for s in scenes] == [
        ("Nồi chiên không dầu 5 lít", "Bếp nhỏ vẫn chiên giòn."),
        ("Chỉ 899 nghìn", "Giá chỉ 899 nghìn."),
    ]
    added = call(mcp_client, token, "add_scene", video_id=video.id)
    assert not added.get("isError"), added
    count = select(func.count(Scene.id)).where(Scene.video_id == video.id, Scene.is_title.is_(False))
    assert db.scalar(count) == 3


GROUP_SCRIPT = {
    "titles": ["5 LOẠI RAU TỐT CHO TIM", "RAU XANH MỖI NGÀY"],
    "title_voice": "Bữa cơm có đủ rau xanh chưa?",
    "title_keywords": ["rau xanh"],
    "title_keywords_en": ["green vegetables"],
    "title_image_prompt": "Fresh green vegetables on a wooden table",
    "scenes": [
        {
            "text": "Rau muống\nGiàu *chất xơ*",
            "seconds": 4,
            "voice": "Rau muống, nhiều chất xơ, tốt cho tiêu hóa.",
            "image_prompt": "A bunch of water spinach",
            "keywords": ["rau muống"],
            "keywords_en": ["water spinach"],
        },
        {"text": "Cải bó xôi", "seconds": 4, "voice": "Cải bó xôi, có sắt.", "keywords": ["cải bó xôi"]},
    ],
    "caption": "Nhà bạn hay ăn rau gì?",
    "hashtags": ["#rauxanh"],
    "affiliates": [],
    "pinned_comment": "Bạn thích rau nào nhất?",
    "self_review": ['"chữa bệnh tim" → "tốt cho tim"'],
    "music_suggestions": ["Windy Hill"],
}


def test_the_assistant_reads_the_groups_whole_script_prompt(mcp_client, db):
    from conftest import first_topic

    from reels_api.claude import BACKDROP_FORMAT, OUTPUT_FORMAT

    _, _, tokens, _ = grant(mcp_client, db)
    group = first_topic(db)
    group.banned_words, group.photo_hint = ["thần dược"], "Ảnh rau đang mọc"
    db.commit()
    read = call(
        mcp_client, tokens["access_token"], "get_script_prompt", topic=" Rau  xanh ", knowledge_topic_id=group.id
    )
    assert not read.get("isError"), read
    prompt = payload(read)["prompt"]
    assert "Rau xanh" in prompt and '"thần dược"' in prompt and "Ảnh rau đang mọc" in prompt
    assert prompt.endswith(OUTPUT_FORMAT) and BACKDROP_FORMAT not in prompt
    single = call(
        mcp_client,
        tokens["access_token"],
        "get_script_prompt",
        topic="Rau xanh",
        knowledge_topic_id=group.id,
        video_mode="single",
    )
    assert payload(single)["prompt"].endswith(BACKDROP_FORMAT)
    group.script_prompt = ""
    db.commit()
    empty = call(mcp_client, tokens["access_token"], "get_script_prompt", topic="Rau", knowledge_topic_id=group.id)
    assert empty["isError"]


def test_a_script_written_from_the_group_prompt_is_saved_like_a_job_and_named_as_the_members_claude(
    mcp_client, db, storage
):
    from conftest import first_topic

    from reels_api.models import Video

    user, _, tokens, _ = grant(mcp_client, db)
    made = call(
        mcp_client,
        tokens["access_token"],
        "create_video_from_group_prompt",
        topic="Rau xanh cho tim",
        knowledge_topic_id=first_topic(db).id,
        script_json="Đây là kịch bản:\n" + json.dumps(GROUP_SCRIPT, ensure_ascii=False),
    )
    assert not made.get("isError"), made
    video = db.scalar(select(Video).where(Video.topic == "Rau xanh cho tim"))
    assert video.has_script and not video.hand_written and video.written_via == "assistant"
    assert video.created_by_id == user.id
    assert video.title_options == GROUP_SCRIPT["titles"]
    assert (video.caption, video.pinned_comment) == ("Nhà bạn hay ăn rau gì?", "Bạn thích rau nào nhất?")
    assert video.self_review == GROUP_SCRIPT["self_review"]
    scenes = db.scalars(select(Scene).where(Scene.video_id == video.id).order_by(Scene.position)).all()
    assert [(s.is_title, s.text, s.voice_text) for s in scenes] == [
        (True, "5 LOẠI RAU TỐT CHO TIM", "Bữa cơm có đủ rau xanh chưa?"),
        (False, "Rau muống\nGiàu *chất xơ*", "Rau muống, nhiều chất xơ, tốt cho tiêu hóa."),
        (False, "Cải bó xôi", "Cải bó xôi, có sắt."),
    ]
    assert scenes[1].keywords_en == ["water spinach"]
    # No script job: the team's AI service was not asked. "Tự tìm ảnh" follows, as after a job.
    kinds = db.scalars(select(Job.kind).where(Job.video_id == video.id)).all()
    assert kinds == ["photos"]
    # The default test connection is ChatGPT's: the video names it, not "Claude".
    assert payload(made)["script_by"] == assistant_writer("ChatGPT")
    assert video.assistant_app == "ChatGPT"


def test_a_script_the_parser_cannot_read_is_refused_and_makes_no_video(mcp_client, db):
    from conftest import first_topic

    from reels_api.models import Video

    _, _, tokens, _ = grant(mcp_client, db)
    refused = call(
        mcp_client,
        tokens["access_token"],
        "create_video_from_group_prompt",
        topic="Không có cảnh",
        knowledge_topic_id=first_topic(db).id,
        script_json=json.dumps({"titles": ["CHỈ CÓ TIÊU ĐỀ"], "scenes": []}),
    )
    assert refused["isError"]
    assert "không có cảnh nội dung nào" in refused["content"][0]["text"]
    assert db.scalar(select(Video).where(Video.topic == "Không có cảnh")) is None


def test_the_assistant_writes_to_a_plan_idea_and_the_idea_gets_the_video(mcp_client, db, storage):
    from conftest import first_topic

    from reels_api.models import TopicPlanItem, Video

    _, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    group = first_topic(db)
    idea = TopicPlanItem(
        knowledge_topic_id=group.id,
        day=2,
        position=1,
        topic="Đau gối khi leo cầu thang",
        pain_group="Xương khớp",
        pain="Gối đau mỗi sáng",
        hook="Sai lầm khi uống nước",
    )
    db.add(idea)
    db.commit()
    listed = payload(call(mcp_client, token, "list_plan_ideas", knowledge_topic_id=group.id))
    assert [row["id"] for row in listed["ideas"]] == [idea.id]
    assert listed["ideas"][0]["hook"] == "Sai lầm khi uống nước"
    read = payload(call(mcp_client, token, "get_script_prompt", knowledge_topic_id=group.id, plan_item_id=idea.id))
    assert read["topic"] == "Đau gối khi leo cầu thang"
    assert all(part in read["prompt"] for part in ("Xương khớp", "Gối đau mỗi sáng", "Sai lầm khi uống nước"))
    made = call(
        mcp_client,
        token,
        "create_video_from_group_prompt",
        knowledge_topic_id=group.id,
        plan_item_id=idea.id,
        script_json=json.dumps(GROUP_SCRIPT, ensure_ascii=False),
    )
    assert not made.get("isError"), made
    video = db.scalar(select(Video).where(Video.topic == "Đau gối khi leo cầu thang"))
    db.refresh(idea)
    assert idea.video_id == video.id and video.written_via == "assistant"
    assert payload(call(mcp_client, token, "list_plan_ideas", knowledge_topic_id=group.id))["ideas"] == []
    again = call(mcp_client, token, "get_script_prompt", knowledge_topic_id=group.id, plan_item_id=idea.id)
    assert again["isError"]


def test_the_assistant_suggests_each_scenes_effects_when_asked(mcp_client, db, storage):
    from conftest import first_topic

    from reels_api.autoedit import EFFECTS_FORMAT
    from reels_api.models import Video

    _, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    group = first_topic(db)
    plain = payload(call(mcp_client, token, "get_script_prompt", topic="Rau", knowledge_topic_id=group.id))
    assert EFFECTS_FORMAT not in plain["prompt"]
    asked = payload(
        call(mcp_client, token, "get_script_prompt", topic="Rau", knowledge_topic_id=group.id, ai_effects=True)
    )
    assert EFFECTS_FORMAT in asked["prompt"]
    script = json.loads(json.dumps(GROUP_SCRIPT))
    script["scenes"][0]["effects"] = {"transition": "slide", "color": None, "sounds": [], "layer": None}
    script["scenes"][1]["effects"] = {"transition": "không có", "color": None, "sounds": [], "layer": None}
    made = call(
        mcp_client,
        token,
        "create_video_from_group_prompt",
        topic="Rau có hiệu ứng",
        knowledge_topic_id=group.id,
        ai_effects=True,
        script_json=json.dumps(script, ensure_ascii=False),
    )
    assert not made.get("isError"), made
    video = db.scalar(select(Video).where(Video.topic == "Rau có hiệu ứng"))
    assert video.ai_effects
    scenes = db.scalars(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position)
    ).all()
    # A preset is put on; anything outside the presets is left out, as after a script job.
    assert scenes[0].transition == "slide" and scenes[1].transition is None


def test_affiliate_products_are_listed_and_only_approved_ones_attach(mcp_client, db, storage):
    from test_affiliate_accounts import product

    from reels_api.models import VideoAffiliateProduct

    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user)
    approved = product(db, user, name="Nồi chiên không dầu")
    draft = product(db, user, name="Nồi chiên mini", status="draft")
    listed = call(mcp_client, token, "list_affiliate_products", query="Nồi chiên")
    assert not listed.get("isError"), listed
    content = payload(listed)
    assert [row["id"] for row in content["products"]] == [approved.id]
    assert content["products"][0]["price"] == 200000
    everything = call(mcp_client, token, "list_affiliate_products", query="Nồi chiên", approved_only=False)
    assert payload(everything)["total"] == 2
    assert call(mcp_client, token, "set_video_products", video_id=video.id, product_ids=[draft.id])["isError"]
    attached = call(mcp_client, token, "set_video_products", video_id=video.id, product_ids=[approved.id])
    assert not attached.get("isError"), attached
    chosen = select(VideoAffiliateProduct.product_id).where(VideoAffiliateProduct.video_id == video.id)
    assert db.scalars(chosen).all() == [approved.id]


def test_the_assistant_lists_my_products_first_and_says_whose_commission_a_teammates_earns(
    mcp_client, db, storage, fakes
):
    from test_affiliate_accounts import live_post, page_of, product

    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    teammate = make_user(db, email="binh@doi.vn", name="Trần Bình")
    other_topic = mcp_client.post("/api/knowledge/topics", json={"name": "Ăn Lành Sống Khỏe"}).json()["topics"][-1]
    mine = product(db, user, name="Gối của An", url="https://s.shopee.vn/an", price=100000)
    theirs = product(db, teammate, name="Gối của Bình", url="https://s.shopee.vn/binh", price=900000)
    elsewhere = product(db, user, name="Gối nhóm khác", price=500000)
    elsewhere.knowledge_topic_id = other_topic["id"]
    db.commit()

    listed = payload(call(mcp_client, token, "list_affiliate_products", query="Gối"))
    assert [row["id"] for row in listed["products"]] == [elsewhere.id, mine.id], "only mine by default"
    assert listed["products"][0]["created_by"] == "Nguyễn Văn An" and listed["products"][0]["mine"] is True
    everyone = payload(call(mcp_client, token, "list_affiliate_products", query="Gối", whose="all"))
    by_id = {row["id"]: row for row in everyone["products"]}
    assert by_id[theirs.id]["mine"] is False and by_id[theirs.id]["created_by"] == "Trần Bình"

    post = live_post(db, storage, user, fakes, page_of(db, teammate))
    video = db.get(Video, post.video_id)
    video.knowledge_topic_id = first_topic(db).id
    db.commit()
    ranked = payload(call(mcp_client, token, "list_affiliate_products", query="Gối", video_id=video.id))
    assert [row["id"] for row in ranked["products"]] == [mine.id, elsewhere.id], "the video's group comes first"

    attached = call(mcp_client, token, "set_video_products", video_id=video.id, product_ids=[mine.id, theirs.id])
    assert not attached.get("isError"), attached
    answer = payload(attached)
    by_id = {row["id"]: row for row in answer["products"]}
    assert by_id[mine.id]["mine"] is True and by_id[mine.id]["commission"][0]["user_name"] == "Nguyễn Văn An"
    assert by_id[theirs.id]["commission"][0]["mine"] is False
    assert len(answer["commission_warnings"]) == 1 and "Trần Bình" in answer["commission_warnings"][0]


def test_attaching_a_teammates_product_to_an_unposted_video_warns_whose_link_it_is(mcp_client, db, storage):
    from test_affiliate_accounts import product

    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    teammate = make_user(db, email="binh@doi.vn", name="Trần Bình")
    video = make_video(db, storage, user)
    theirs = product(db, teammate, name="Gối của Bình", url="https://s.shopee.vn/binh")
    answer = payload(call(mcp_client, token, "set_video_products", video_id=video.id, product_ids=[theirs.id]))
    assert answer["products"][0]["mine"] is False and answer["products"][0]["commission"] == []
    assert len(answer["commission_warnings"]) == 1 and "Trần Bình" in answer["commission_warnings"][0]
    tiktok = make_video(db, storage, user)
    tiktok.platform = "tiktok"
    db.commit()
    tea = product(db, teammate, name="Trà", platform="tiktok_shop", url="https://www.tiktok.com/view/product/1")
    answer = payload(call(mcp_client, token, "set_video_products", video_id=tiktok.id, product_ids=[tea.id]))
    assert answer["products"][0]["mine"] is False and answer["commission_warnings"] == [], "no comment on TikTok"


def test_a_scene_takes_a_photo_from_a_link_and_a_read_only_connection_cannot(
    mcp_client, db, storage, fakes, monkeypatch
):
    from reels_api import remote_media
    from reels_api.models import McpConnection

    monkeypatch.setattr(remote_media, "is_public", lambda address: True)
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user)
    scene = db.scalar(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position)
    )
    url = fakes.image_url("noi-chien")
    saved = call(mcp_client, token, "set_scene_media_from_link", scene_id=scene.id, url=url)
    assert not saved.get("isError"), saved
    db.refresh(scene)
    assert scene.image_source == url and storage.exists(scene.image_key)
    row = db.scalar(select(McpConnection))
    row.scopes = "reels:read"
    db.commit()
    assert call(mcp_client, token, "set_scene_media_from_link", scene_id=scene.id, url=url)["isError"]


def test_the_consent_answer_sends_the_browser_on_with_a_link_it_can_also_click(mcp_client, db):
    """Regression: production's web proxy followed the 303 to Claude's callback itself, so the member saw Claude's
    "Page not found" on /api/mcp/oauth/consent and the connection never finished."""
    make_user(db)
    login(mcp_client)
    cid = register(mcp_client).json()["client_id"]
    ticket = ticket_of(authorize(mcp_client, cid))
    approved = mcp_client.post(
        "/api/mcp/oauth/consent", data={"ticket": ticket, "decision": "allow"}, follow_redirects=False
    )
    target = callback_of(approved)
    assert target.startswith(CALLBACK + "?")
    assert parse_qs(urlparse(target).query)["state"] == ["client-state"]
    assert approved.text.count(escape(target, quote=True)) == 2  # the refresh and the link
    assert approved.headers["cache-control"] == "no-store"


def test_the_assistant_reads_todays_semi_automatic_runs_and_cannot_approve_them(mcp_client, db, storage):
    from reels_api import fanpages, plans
    from reels_api.models import AutoRun

    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user)
    page = fanpages.save(db, "111", "Ăn Lành Sống Khỏe", "EAAB-token-111", user.id)
    db.flush()
    db.add(
        AutoRun(
            fanpage_id=page.id,
            day=plans.today(),
            idea_topic="Ngâm chân nước ấm",
            video_id=video.id,
            status="ready",
            stage="done",
            banned=["Có từ cấm: “thần dược”"],
        )
    )
    db.commit()
    tools = {tool["name"]: tool for tool in rpc(mcp_client, token, "tools/list").json()["result"]["tools"]}
    assert tools["list_auto_runs"]["annotations"]["readOnlyHint"] is True
    assert not any("approve" in name for name in tools)
    [run] = payload(call(mcp_client, token, "list_auto_runs"))["runs"]
    assert (run["status"], run["idea_topic"], run["video"]["id"]) == ("ready", "Ngâm chân nước ấm", video.id)
    assert run["banned"] == ["Có từ cấm: “thần dược”"] and run["can_decide"] is True
