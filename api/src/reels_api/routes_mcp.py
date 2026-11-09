"""OAuth authorization-code + S256 PKCE for the private ChatGPT and Claude connections."""

import logging
import secrets
from datetime import timedelta
from html import escape
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .mcp_auth import (
    CONNECTION_LIFETIME,
    MAX_REDIRECTS,
    SCOPES,
    Enabled,
    allowed_redirect,
    app_of,
    member_session,
    oauth_error,
    pkce,
    redirect_matches,
    registered,
    require_enabled,
    rotate_tokens,
    valid_verifier,
)
from .models import McpAuthorization, McpClient, McpConnection, Session
from .security import hash_session_token, new_session_token
from .sessions import COOKIE_NAME, current_member, now

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Enabled])
PREFIX = "/api/mcp/oauth"
PRIVATE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}
HTML_HEADERS = {
    **PRIVATE_HEADERS,
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def clip(value: str) -> str:
    """At most 300 characters of what an unauthenticated client sent, so one request cannot flood the log."""
    return value[:300]


def page(title: str, content: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        '<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        f"<title>{escape(title)} · Reels Studio</title>"
        f"<main><small>Reels Studio</small><h1>{escape(title)}</h1>{content}</main></html>",
        status_code=status,
        headers=HTML_HEADERS,
    )


@router.get("/.well-known/oauth-protected-resource/api/mcp")
def resource_metadata() -> dict:
    url = require_enabled()
    return {"resource": url, "authorization_servers": [url + "/oauth"], "scopes_supported": sorted(SCOPES)}


@router.get("/.well-known/oauth-authorization-server/api/mcp/oauth")
def authorization_metadata() -> dict:
    url = require_enabled() + "/oauth"
    return {
        "issuer": url,
        "authorization_endpoint": url + "/authorize",
        "token_endpoint": url + "/token",
        "registration_endpoint": url + "/register",
        "revocation_endpoint": url + "/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": sorted(SCOPES),
        "authorization_response_iss_parameter_supported": True,
    }


class Registration(BaseModel):
    redirect_uris: list[str] = Field(min_length=1, max_length=MAX_REDIRECTS)
    token_endpoint_auth_method: str = "none"
    grant_types: list[str] = Field(default=["authorization_code", "refresh_token"], max_length=2)
    response_types: list[str] = Field(default=["code"], max_length=1)
    client_name: str = Field(default="", max_length=100)


@router.post(PREFIX + "/register", status_code=201)
def register(body: Registration, db: DbSession = Depends(get_db)) -> JSONResponse:
    redirects = list(dict.fromkeys(body.redirect_uris))
    if (
        not all(allowed_redirect(uri) for uri in redirects)
        or body.token_endpoint_auth_method != "none"
        or set(body.grant_types) - {"authorization_code", "refresh_token"}
        or body.response_types != ["code"]
    ):
        # Kept for good: it is how a new assistant's exact callback is learnt before it joins the allowlist, and an
        # audit of refused clients. Registration metadata is public (no secret is sent); %r keeps one line per refusal.
        log.warning(
            "MCP registration refused: redirect_uris=%r client_name=%r token_endpoint_auth_method=%r grant_types=%r "
            "response_types=%r",
            [clip(uri) for uri in redirects],
            body.client_name,
            clip(body.token_endpoint_auth_method),
            [clip(kind) for kind in body.grant_types],
            [clip(kind) for kind in body.response_types],
        )
        raise oauth_error(
            "invalid_client_metadata",
            "Chỉ hỗ trợ kết nối ChatGPT, Claude, Claude Code và Muse với callback đã cho phép",
        )
    client = McpClient(id=new_session_token(), redirect_uri=" ".join(redirects))
    db.add(client)
    db.commit()
    return JSONResponse(
        {
            "client_id": client.id,
            "client_name": app_of(redirects[0]),
            "redirect_uris": redirects,
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
        status_code=201,
        headers=PRIVATE_HEADERS,
    )


@router.get(PREFIX + "/authorize", response_class=HTMLResponse)
def authorize(request: Request, db: DbSession = Depends(get_db)):
    query = request.query_params
    client = db.get(McpClient, query.get("client_id", ""))
    resource = require_enabled()
    scopes = query.get("scope", "reels:read").split()
    challenge = query.get("code_challenge", "")
    if client is None:
        # A client that never registered here (an id it made up, or a metadata document URL) is learnt from this.
        log.warning(
            "MCP authorize from an unknown client: client_id=%r redirect_uri=%r",
            clip(query.get("client_id", "")),
            clip(query.get("redirect_uri", "")),
        )
    if (
        client is None
        or not redirect_matches(client.redirect_uri, query.get("redirect_uri", ""))
        or query.get("response_type") != "code"
        or query.get("code_challenge_method") != "S256"
        or len(challenge) != 43
        or not valid_verifier(challenge)
        or query.get("resource") != resource
        or "reels:read" not in scopes
        or set(scopes) - SCOPES
        or len(query.get("state", "")) > 2048
    ):
        raise oauth_error("invalid_request", "Yêu cầu cấp quyền không hợp lệ")
    session_id = db.scalar(
        select(Session.id).where(Session.token_hash == hash_session_token(request.cookies.get(COOKIE_NAME, "")))
    )
    session = member_session(db, session_id) if session_id else None
    if session is None:
        # Signing in happens in this same tab and comes back here (the login page's `next`): opened in another tab,
        # it left members on the video list, and the request that asked for consent was never finished.
        again = PREFIX + "/authorize?" + str(request.query_params)
        return page(
            f"Đăng nhập để kết nối {app_of(query['redirect_uri'])}",
            "<p>Đăng nhập Reels Studio (hoặc đổi mật khẩu tạm), rồi bạn sẽ quay lại đây để cho phép kết nối.</p>"
            f'<p><a href="{escape("/login?" + urlencode({"next": again}), quote=True)}">Đăng nhập Reels Studio</a></p>'
            f'<p><a href="{escape(again, quote=True)}">Tôi đã đăng nhập, tiếp tục</a></p>',
            status=401,
        )
    db.execute(delete(McpAuthorization).where(McpAuthorization.expires_at <= now()))
    ticket = new_session_token()
    db.add(
        McpAuthorization(
            ticket_hash=hash_session_token(ticket),
            client_id=client.id,
            session_id=session.id,
            challenge=challenge,
            resource=resource,
            scopes=" ".join(sorted(set(scopes))),
            state=query.get("state", ""),
            redirect_uri=query["redirect_uri"],
            expires_at=now() + timedelta(minutes=10),
        )
    )
    db.commit()
    return consent_page(session, ticket, query["redirect_uri"], scopes)


def consent_page(session: Session, ticket: str, redirect: str, scopes: list[str]) -> HTMLResponse:
    """The consent screen, served by the authorize request itself. It used to send the member on to the web app's
    /chatgpt#ticket=..., which read the ticket in the browser; in production the consent never showed there and the
    connection could not be finished, so nothing on the way can lose the ticket now: it sits in this page's form."""
    app = app_of(redirect)
    host = urlsplit(redirect)
    loopback = (
        '<p class="warn"><strong>Kết nối với một chương trình trên máy tính.</strong> Chỉ cho phép nếu bạn vừa tự kết '
        "nối Reels Studio trong Claude Code trên máy này. Một chương trình khác trên máy cũng có thể nhận địa chỉ này.</p>"
        if app == "Claude Code"
        else ""
    )
    write = (
        f'<p class="warn"><strong>Quyền sửa và tạo công việc.</strong> {escape(app)} còn được sửa chữ, lời đọc, '
        "caption; tạo video, gắn ảnh hoặc clip từ link, gắn sản phẩm và yêu cầu render. Tạo kịch bản bằng AI của "
        "nhóm và giọng đọc có thể dùng phí dịch vụ AI của nhóm.</p>"
        if "reels:write" in scopes
        else ""
    )
    response = page(
        f"Cho phép {app} kết nối?",
        f"<p>Bạn đang dùng tài khoản <strong>{escape(session.user.email)}</strong>. Quyền sẽ được gửi về "
        f"<code>{escape(host.netloc)}</code>.</p>{loopback}"
        f"<p>{escape(app)} được đọc video, kịch bản, nhóm chủ đề, sản phẩm affiliate và trạng thái công việc của cả "
        f"nhóm.</p>{write}"
        "<p>Kết nối không được đăng bài, xóa video hoặc thay đổi tài khoản và API key. Quyền hết hạn sau tối đa 30 "
        "ngày và mất hiệu lực khi phiên đăng nhập này bị thu hồi.</p>"
        f'<form method="post" action="{PREFIX}/consent">'
        f'<input type="hidden" name="ticket" value="{escape(ticket, quote=True)}">'
        '<button type="submit" name="decision" value="allow">Cho phép kết nối</button> '
        '<button type="submit" name="decision" value="deny">Từ chối</button></form>',
    )
    # The consent answer redirects to the app's callback: the form may go to this site and on to that origin only.
    response.headers["Content-Security-Policy"] = HTML_HEADERS["Content-Security-Policy"].replace(
        "form-action 'self'", f"form-action 'self' {host.scheme}://{host.netloc}"
    )
    # "no-referrer" makes browsers send `Origin: null` with the form, which the CSRF guard refuses.
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@router.get("/api/mcp/config")
def connection_config(me: Session = Depends(current_member)) -> dict:
    return {"server_url": require_enabled()}


@router.get("/api/mcp/authorizations/{ticket}")
def authorization_details(
    ticket: str, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> JSONResponse:
    auth = db.get(McpAuthorization, hash_session_token(ticket))
    if (
        auth is None
        or auth.session_id != me.id
        or auth.expires_at <= now()
        or auth.code_hash
        or auth.resource != require_enabled()
    ):
        raise oauth_error()
    redirect = return_to(auth)
    return JSONResponse(
        {
            "email": me.user.email,
            "scopes": auth.scopes.split(),
            "app": app_of(redirect),
            # The MCP spec asks the consent screen to show where the grant goes, and to warn for a loopback one.
            "redirect_host": urlsplit(redirect).netloc,
            "loopback": app_of(redirect) == "Claude Code",
        },
        headers=PRIVATE_HEADERS,
    )


def return_to(auth: McpAuthorization) -> str:
    # A grant from before 0047 has no callback of its own: its client had exactly one.
    return auth.redirect_uri or registered(auth.client.redirect_uri)[0]


def callback(auth: McpAuthorization, **values) -> HTMLResponse:
    """The consent answer, sent on to the app's callback by the browser itself. Never a 303: in production the web
    app (OpenNext on Cloudflare) proxies /api with a fetch that follows redirects, so it fetched Claude's callback
    server-side and showed Claude's "Page not found" on this URL. A refresh (no script: the page's CSP allows none)
    and a link the member can click both go there."""
    params = {"state": auth.state, "iss": require_enabled() + "/oauth", **values}
    target = escape(return_to(auth) + "?" + urlencode(params), quote=True)
    app = app_of(return_to(auth))
    return page(
        f"Đang quay lại {app}",
        f'<meta http-equiv="refresh" content="0;url={target}">'
        f'<p>Nếu trang không tự chuyển, <a href="{target}">bấm vào đây để quay lại {escape(app)}</a>.</p>',
    )


@router.post(PREFIX + "/consent")
def consent(
    ticket: str = Form(max_length=128),
    decision: str = Form(max_length=10),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> HTMLResponse:
    auth = db.scalar(
        select(McpAuthorization).where(McpAuthorization.ticket_hash == hash_session_token(ticket)).with_for_update()
    )
    if (
        auth is None
        or auth.session_id != me.id
        or auth.expires_at <= now()
        or auth.code_hash
        or auth.resource != require_enabled()
    ):
        raise oauth_error()
    if decision != "allow":
        response = callback(auth, error="access_denied")
        db.delete(auth)
        db.commit()
        return response
    code = new_session_token()
    auth.code_hash, auth.expires_at = hash_session_token(code), now() + timedelta(minutes=2)
    response = callback(auth, code=code)
    db.commit()
    return response


@router.post(PREFIX + "/token")
def token(
    grant_type: str = Form(max_length=40),
    client_id: str = Form(max_length=128),
    resource: str = Form(max_length=1000),
    code: str = Form(default="", max_length=128),
    redirect_uri: str = Form(default="", max_length=1000),
    code_verifier: str = Form(default="", max_length=128),
    refresh_token: str = Form(default="", max_length=128),
    db: DbSession = Depends(get_db),
) -> JSONResponse:
    if resource != require_enabled():
        raise oauth_error("invalid_target", "Quyền kết nối không dành cho máy chủ này")
    client = db.get(McpClient, client_id)
    if client is None:
        raise oauth_error("invalid_client")
    if grant_type == "authorization_code":
        auth = db.scalar(
            select(McpAuthorization).where(McpAuthorization.code_hash == hash_session_token(code)).with_for_update()
        )
        if (
            auth is None
            or auth.client_id != client.id
            or auth.resource != resource
            or auth.expires_at <= now()
            or redirect_uri != return_to(auth)
            or not valid_verifier(code_verifier)
            or not secrets.compare_digest(pkce(code_verifier), auth.challenge)
            or member_session(db, auth.session_id) is None
        ):
            raise oauth_error()
        connection = McpConnection(
            session_id=auth.session_id,
            client_id=client.id,
            scopes=auth.scopes,
            resource=resource,
            expires_at=now() + CONNECTION_LIFETIME,
        )
        db.delete(auth)
        db.add(connection)
    elif grant_type == "refresh_token":
        connection = db.scalar(
            select(McpConnection)
            .where(McpConnection.refresh_hash == hash_session_token(refresh_token))
            .with_for_update()
        )
        if (
            connection is None
            or connection.client_id != client.id
            or connection.resource != resource
            or connection.expires_at <= now()
            or member_session(db, connection.session_id) is None
        ):
            raise oauth_error()
        # Sliding expiry: a connection in use lives on; one left unused for CONNECTION_LIFETIME has ended above.
        connection.expires_at = now() + CONNECTION_LIFETIME
    else:
        raise oauth_error("unsupported_grant_type", "Kiểu cấp quyền không được hỗ trợ")
    tokens = rotate_tokens(connection)
    db.commit()
    return JSONResponse(tokens, headers=PRIVATE_HEADERS)


@router.post(PREFIX + "/revoke")
def revoke(
    token: str = Form(max_length=128), client_id: str = Form(max_length=128), db: DbSession = Depends(get_db)
) -> dict:
    digest = hash_session_token(token)
    db.execute(
        delete(McpConnection).where(
            McpConnection.client_id == client_id,
            or_(McpConnection.access_hash == digest, McpConnection.refresh_hash == digest),
        )
    )
    db.commit()
    return {}


def own_connections(db: DbSession, me: Session):
    return db.scalars(
        select(McpConnection).join(Session).where(Session.user_id == me.user_id).order_by(McpConnection.id)
    ).all()


@router.get("/api/mcp/connections")
def connections(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    return [
        {
            "id": row.id,
            "app": app_of(registered(row.client.redirect_uri)[0]),
            "scopes": row.scopes,
            "expires_at": row.expires_at.isoformat(),
        }
        for row in own_connections(db, me)
    ]


@router.delete("/api/mcp/connections/{connection_id}")
def disconnect(connection_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    row = next((row for row in own_connections(db, me) if row.id == connection_id), None)
    if row is None:
        raise oauth_error("connection_not_found", "Không tìm thấy kết nối của bạn")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/api/mcp/manage")
def manage(me: Session = Depends(current_member)):
    return RedirectResponse("/settings/mcp", status_code=303, headers=PRIVATE_HEADERS)
