"""TikTok's Login Kit and Content Posting API (issue #46), reached only through the fake service."""

import html
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import client_for, login, make_user
from fake_services import TIKTOK_CLIENT_KEY, TIKTOK_CODE, TIKTOK_OPEN_ID
from sqlalchemy import select, text

from reels_api import tiktok
from reels_api.models import AffiliateAccount, TikTokConnection, TikTokOAuthState

# --- The client ---


def test_authorize_url_names_the_app_its_scopes_and_the_registered_callback(fakes):
    url = tiktok.authorize_url("state-123")
    parts = urlsplit(url)
    query = {name: values[0] for name, values in parse_qs(parts.query).items()}
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://www.tiktok.com/v2/auth/authorize/"
    assert query == {
        "client_key": TIKTOK_CLIENT_KEY,
        "scope": "user.info.basic,video.upload,video.publish",
        "response_type": "code",
        "redirect_uri": "https://reels.quangdang.xyz/api/tiktok/oauth/callback",
        "state": "state-123",
    }


def test_without_credentials_every_call_says_what_to_configure(monkeypatch):
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "")
    for call in (lambda: tiktok.authorize_url("s"), lambda: tiktok.exchange_code("c"), lambda: tiktok.refresh("r")):
        with pytest.raises(tiktok.TikTokError) as caught:
            call()
        assert caught.value.message == "Chưa cấu hình TIKTOK_CLIENT_KEY/TIKTOK_CLIENT_SECRET trong .env"


def test_code_exchange_and_user_info(fakes):
    tokens = tiktok.exchange_code(TIKTOK_CODE)
    assert tokens.open_id == TIKTOK_OPEN_ID
    assert tokens.access_token and tokens.refresh_token
    assert tokens.access_token not in repr(tokens) and tokens.refresh_token not in repr(tokens)
    user = tiktok.user_info(tokens.access_token)
    assert (user.open_id, user.username, user.display_name) == (TIKTOK_OPEN_ID, "anlanhsk", "An Lành SK")


def test_a_bad_code_is_named(fakes):
    with pytest.raises(tiktok.TikTokError) as caught:
        tiktok.exchange_code("used-code")
    assert caught.value.message == "Mã ủy quyền TikTok không hợp lệ hoặc đã hết hạn, hãy kết nối lại"
    assert "invalid_grant" in caught.value.detail


def test_refresh_rotates_the_refresh_token(fakes):
    first = tiktok.exchange_code(TIKTOK_CODE)
    second = tiktok.refresh(first.refresh_token)
    assert second.refresh_token != first.refresh_token
    assert second.access_token != first.access_token
    # The old refresh token is spent: only the new one works.
    with pytest.raises(tiktok.TikTokError) as caught:
        tiktok.refresh(first.refresh_token)
    assert caught.value.expired
    assert caught.value.message == "Kết nối TikTok đã hết hạn, hãy kết nối lại"
    tiktok.refresh(second.refresh_token)


def test_an_invalid_access_token_reads_as_an_expired_connection(fakes):
    with pytest.raises(tiktok.TikTokError) as caught:
        tiktok.user_info("not-a-token")
    assert caught.value.expired
    assert "access_token_invalid" in caught.value.detail


def test_rate_limit_and_unaudited_refusals_are_translated(fakes, tmp_path):
    token = tiktok.exchange_code(TIKTOK_CODE).access_token
    fakes.tiktok_init_error = "rate_limit_exceeded"
    with pytest.raises(tiktok.TikTokError) as caught:
        tiktok.init_inbox(token, 10, 10, 1)
    assert caught.value.message == "TikTok đang giới hạn tốc độ, thử lại sau"
    fakes.tiktok_init_error = None
    fakes.tiktok_unaudited = True
    info = {"title": "x", "privacy_level": "PUBLIC_TO_EVERYONE", "is_aigc": True}
    with pytest.raises(tiktok.TikTokError) as caught:
        tiktok.init_direct(token, info, 10, 10, 1)
    assert caught.value.message.startswith("App chưa qua duyệt TikTok")
    assert "unaudited_client_can_only_post_to_private_accounts" in caught.value.detail


def test_chunk_plan_follows_tiktok_rules():
    assert tiktok.chunk_plan(12 * 1024 * 1024) == (12 * 1024 * 1024, 1)
    assert tiktok.chunk_plan(64 * 1024 * 1024) == (64 * 1024 * 1024, 1)
    size = 95 * 1024 * 1024
    chunk, count = tiktok.chunk_plan(size)
    assert (chunk, count) == (10 * 1024 * 1024, 9)  # the last chunk takes the remaining 15 MB


def test_upload_in_chunks_then_the_status_reports_the_inbox(fakes, tmp_path, monkeypatch):
    monkeypatch.setattr(tiktok, "SINGLE_CHUNK_LIMIT", 10)
    monkeypatch.setattr(tiktok, "CHUNK_SIZE", 4)
    path = tmp_path / "v.mp4"
    path.write_bytes(b"0123456789abc")  # 13 bytes: chunks of 4, 4 and 5
    token = tiktok.exchange_code(TIKTOK_CODE).access_token
    size = path.stat().st_size
    chunk, count = tiktok.chunk_plan(size)
    assert (chunk, count) == (4, 3)
    upload = tiktok.init_inbox(token, size, chunk, count)
    assert tiktok.publish_status(token, upload.publish_id)["status"] == "PROCESSING_UPLOAD"
    tiktok.upload_chunks(upload.upload_url, path, chunk, count)
    assert fakes.tiktok_posts[upload.publish_id]["bytes"] == 13
    assert fakes.tiktok_calls.count("upload") == 3
    assert tiktok.publish_status(token, upload.publish_id)["status"] == "SEND_TO_USER_INBOX"


def test_creator_info_lists_the_privacy_levels(fakes):
    token = tiktok.exchange_code(TIKTOK_CODE).access_token
    fakes.tiktok_privacy_options = ["SELF_ONLY"]
    assert tiktok.creator_info(token).privacy_level_options == ["SELF_ONLY"]


def test_an_unknown_publish_id_is_named(fakes):
    token = tiktok.exchange_code(TIKTOK_CODE).access_token
    with pytest.raises(tiktok.TikTokError) as caught:
        tiktok.publish_status(token, "v_pub_file~missing")
    assert caught.value.code == "invalid_publish_id"


def test_post_title_is_the_caption_then_the_hashtags_cut_at_tiktoks_limit():
    assert tiktok.post_title("Ba món tốt cho tim", ["#suckhoe", "#tim"]) == "Ba món tốt cho tim #suckhoe #tim"
    assert len(tiktok.post_title("a" * 3000, ["#x"])) == 2200


# --- Connecting a member's TikTok account ---


def _state_of(response) -> str:
    """ "Kết nối TikTok" answers with TikTok's authorize URL; the browser goes there itself."""
    assert response.status_code == 200, response.text
    return parse_qs(urlsplit(response.json()["url"]).query)["state"][0]


def _connect(client, code=TIKTOK_CODE):
    """ "Kết nối TikTok", TikTok's consent, and the way back: the callback's redirect."""
    state = _state_of(client.get("/api/tiktok/oauth/start", follow_redirects=False))
    return client.get(f"/api/tiktok/oauth/callback?code={code}&state={state}", follow_redirects=False)


REFRESH = re.compile(r'<meta http-equiv="refresh" content="0;url=([^"]+)">')


def _outcome(response) -> dict:
    """The callback's page, which sends the browser back to "Tài khoản affiliate" by itself."""
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    found = REFRESH.search(response.text)
    assert found, response.text
    parts = urlsplit(html.unescape(found.group(1)))
    assert parts.path == "/settings/affiliate-accounts"
    return {name: values[0] for name, values in parse_qs(parts.query).items()}


def test_neither_start_nor_callback_answers_with_a_redirect(fakes, db, client):
    """In production the web's /api proxy (Cloudflare Workers) follows a redirect itself instead of handing it to the
    browser: TikTok's page was fetched by the proxy, and the way back to the settings page ended in the api's 404."""
    make_user(db)
    login(client)
    start = client.get("/api/tiktok/oauth/start", follow_redirects=False)
    assert not start.is_redirect and start.status_code == 200
    state = _state_of(start)
    back = client.get(f"/api/tiktok/oauth/callback?code={TIKTOK_CODE}&state={state}", follow_redirects=False)
    assert not back.is_redirect
    anonymous = client.get("/api/tiktok/oauth/callback?code=x&state=y", follow_redirects=False)
    assert not anonymous.is_redirect


def test_start_sends_the_member_to_tiktok_with_a_hashed_one_use_state(fakes, db, client):
    make_user(db)
    login(client)
    state = _state_of(client.get("/api/tiktok/oauth/start", follow_redirects=False))
    rows = db.scalars(select(TikTokOAuthState)).all()
    assert len(rows) == 1 and rows[0].state_hash != state and state not in rows[0].state_hash


def test_start_needs_a_member(fakes, client):
    assert client.get("/api/tiktok/oauth/start", follow_redirects=False).status_code == 401


def test_start_without_credentials_says_what_to_configure(db, client, monkeypatch):
    make_user(db)
    login(client)
    response = client.get("/api/tiktok/oauth/start", follow_redirects=False)
    assert response.status_code == 409
    assert response.json()["message"] == "Chưa cấu hình TIKTOK_CLIENT_KEY/TIKTOK_CLIENT_SECRET trong .env"


def test_callback_saves_encrypted_tokens_on_a_new_tiktok_account_of_the_member(fakes, db, client):
    user = make_user(db)
    login(client)
    assert _outcome(_connect(client)) == {"tiktok": "connected"}
    connection = db.scalar(select(TikTokConnection))
    account = db.get(AffiliateAccount, connection.affiliate_account_id)
    assert (account.owner_id, account.platform, account.active) == (user.id, "tiktok", True)
    assert (account.name, account.profile_url) == ("An Lành SK", "https://www.tiktok.com/@anlanhsk")
    assert (connection.owner_id, connection.open_id, connection.username) == (user.id, TIKTOK_OPEN_ID, "anlanhsk")
    # No column holds a token as TikTok gave it.
    issued = set(fakes.tiktok_access) | set(fakes.tiktok_refresh)
    raw = db.execute(text("SELECT * FROM tiktok_connections")).mappings().one()
    assert not any(token in str(value) for value in raw.values() for token in issued)
    # The state is used up: the same answer cannot connect twice.
    assert db.scalar(select(TikTokOAuthState)) is None


def test_callback_joins_the_members_account_with_that_username(fakes, db, client):
    make_user(db)
    login(client)
    added = client.post(
        "/api/affiliate-accounts",
        json={"platform": "tiktok", "name": "Kênh của An", "profile_url": "https://www.tiktok.com/@AnLanhSK"},
    ).json()
    _connect(client)
    connection = db.scalar(select(TikTokConnection))
    assert connection.affiliate_account_id == added["id"]
    assert len(db.scalars(select(AffiliateAccount)).all()) == 1
    # Tài khoản affiliate shows the connection, without any part of a token.
    listed = client.get("/api/affiliate-accounts").json()[0]["tiktok_connection"]
    assert listed["username"] == "anlanhsk" and listed["needs_reconnect"] is False
    body = client.get("/api/affiliate-accounts").text
    assert not any(
        token in body or token[-6:] in body for token in set(fakes.tiktok_access) | set(fakes.tiktok_refresh)
    )


def test_a_wrong_or_expired_state_connects_nothing(fakes, db, client):
    user = make_user(db)
    login(client)
    response = client.get(f"/api/tiktok/oauth/callback?code={TIKTOK_CODE}&state=made-up", follow_redirects=False)
    assert _outcome(response)["tiktok"] == "error"
    state = _state_of(client.get("/api/tiktok/oauth/start", follow_redirects=False))
    db.execute(text("UPDATE tiktok_oauth_states SET expires_at = now() - interval '1 second'"))
    db.commit()
    response = client.get(f"/api/tiktok/oauth/callback?code={TIKTOK_CODE}&state={state}", follow_redirects=False)
    assert _outcome(response)["message"].startswith("Lần kết nối TikTok này đã hết hạn")
    assert db.scalar(select(TikTokConnection)) is None
    assert db.scalar(select(AffiliateAccount).where(AffiliateAccount.owner_id == user.id)) is None
    assert "/v2/oauth/token/" not in fakes.tiktok_calls


def test_another_members_state_or_no_session_connects_nothing(fakes, db, app, client):
    make_user(db)
    make_user(db, email="binh@doi.vn", name="Bình")
    login(client)
    state = _state_of(client.get("/api/tiktok/oauth/start", follow_redirects=False))
    other = client_for(app)
    login(other, email="binh@doi.vn")
    response = other.get(f"/api/tiktok/oauth/callback?code={TIKTOK_CODE}&state={state}", follow_redirects=False)
    assert _outcome(response)["tiktok"] == "error"
    anonymous = client_for(app)
    response = anonymous.get(f"/api/tiktok/oauth/callback?code={TIKTOK_CODE}&state=x", follow_redirects=False)
    assert _outcome(response)["message"].startswith("Phiên đăng nhập đã hết")
    assert db.scalar(select(TikTokConnection)) is None


def test_a_refused_consent_or_a_bad_code_connects_nothing(fakes, db, client):
    make_user(db)
    login(client)
    state = _state_of(client.get("/api/tiktok/oauth/start", follow_redirects=False))
    response = client.get(f"/api/tiktok/oauth/callback?error=access_denied&state={state}", follow_redirects=False)
    assert _outcome(response)["message"].startswith("Bạn chưa cho phép")
    assert _outcome(_connect(client, code="stale"))["message"].startswith("Mã ủy quyền TikTok không hợp lệ")
    assert db.scalar(select(TikTokConnection)) is None


def test_a_tiktok_account_another_member_connected_is_refused(fakes, db, app, client):
    make_user(db)
    make_user(db, email="binh@doi.vn", name="Bình")
    login(client)
    _connect(client)
    other = client_for(app)
    login(other, email="binh@doi.vn")
    outcome = _outcome(_connect(other))
    assert outcome == {"tiktok": "error", "message": "Tài khoản TikTok @anlanhsk đã được một thành viên khác kết nối"}
    connections = db.scalars(select(TikTokConnection)).all()
    assert len(connections) == 1 and connections[0].owner_id != db.scalar(
        text("SELECT id FROM users WHERE email = 'binh@doi.vn'")
    )


def test_connecting_again_refreshes_the_same_connection(fakes, db, client):
    make_user(db)
    login(client)
    _connect(client)
    first = db.scalar(select(TikTokConnection))
    old = first.access_token_encrypted
    _connect(client)
    db.expire_all()
    rows = db.scalars(select(TikTokConnection)).all()
    assert len(rows) == 1 and rows[0].id == first.id and rows[0].access_token_encrypted != old


def test_disconnect_forgets_the_tokens_keeps_the_account_and_is_owner_only(fakes, db, app, client):
    make_user(db)
    make_user(db, email="binh@doi.vn", name="Bình")
    login(client)
    _connect(client)
    connection = db.scalar(select(TikTokConnection))
    other = client_for(app)
    login(other, email="binh@doi.vn")
    assert other.delete(f"/api/tiktok/connections/{connection.id}").status_code == 404
    assert client.delete(f"/api/tiktok/connections/{connection.id}").status_code == 200
    assert db.scalar(select(TikTokConnection)) is None
    assert db.get(AffiliateAccount, connection.affiliate_account_id) is not None
    assert fakes.tiktok_revoked  # revoked on TikTok too


def test_disconnect_goes_through_even_when_tiktok_refuses_the_revoke(fakes, db, client, monkeypatch):
    make_user(db)
    login(client)
    _connect(client)
    connection = db.scalar(select(TikTokConnection))
    monkeypatch.setenv("TIKTOK_API_URL", "http://127.0.0.1:9/unreachable")
    assert client.delete(f"/api/tiktok/connections/{connection.id}").status_code == 200
    assert db.scalar(select(TikTokConnection)) is None
