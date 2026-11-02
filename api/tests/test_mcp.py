"""Exercise the OAuth boundary and real MCP transport without any external AI calls."""

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import WEB_ORIGIN, login, make_user, make_video
from fastapi.testclient import TestClient
from sqlalchemy import select

from reels_api.db import get_db
from reels_api.main import create_app
from reels_api.models import Job, Scene

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
    assert response.status_code == 303, response.text
    return parse_qs(urlparse(response.headers["location"]).fragment)["ticket"][0]


def grant(client, db):
    user = make_user(db)
    login(client)
    client_id = register(client).json()["client_id"]
    page = authorize(client, client_id)
    assert page.status_code == 303, page.text
    ticket = ticket_of(page)
    approved = client.post(
        "/api/mcp/oauth/consent", data={"ticket": ticket, "decision": "allow"}, follow_redirects=False
    )
    assert approved.status_code == 303, approved.text
    params = parse_qs(urlparse(approved.headers["location"]).query)
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
    assert parse_qs(urlparse(denied.headers["location"]).query)["error"] == ["access_denied"]
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
    code = parse_qs(urlparse(approved.headers["location"]).query)["code"][0]
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


def test_consent_opens_the_app_and_is_visible_only_to_its_member_session(mcp_client, db):
    make_user(db)
    login(mcp_client)
    cid = register(mcp_client).json()["client_id"]
    response = authorize(mcp_client, cid)
    assert response.status_code == 303
    destination = urlparse(response.headers["location"])
    assert destination.path == "/chatgpt"
    ticket = parse_qs(destination.fragment)["ticket"][0]
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
