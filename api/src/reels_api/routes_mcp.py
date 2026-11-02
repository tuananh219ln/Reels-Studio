"""OAuth authorization-code + S256 PKCE for the private ChatGPT connection."""

import secrets
from datetime import timedelta
from html import escape
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .mcp_auth import (
    CALLBACK,
    CONNECTION_LIFETIME,
    SCOPES,
    Enabled,
    member_session,
    oauth_error,
    pkce,
    require_enabled,
    rotate_tokens,
    valid_verifier,
)
from .models import McpAuthorization, McpClient, McpConnection, Session
from .security import hash_session_token, new_session_token
from .sessions import COOKIE_NAME, current_member, now

router = APIRouter(dependencies=[Enabled])
PREFIX = "/api/mcp/oauth"
PRIVATE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}
HTML_HEADERS = {
    **PRIVATE_HEADERS,
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


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
    redirect_uris: list[str] = Field(max_length=1)
    token_endpoint_auth_method: str = "none"
    grant_types: list[str] = Field(default=["authorization_code", "refresh_token"], max_length=2)
    response_types: list[str] = Field(default=["code"], max_length=1)
    client_name: str = Field(default="ChatGPT", max_length=100)


@router.post(PREFIX + "/register", status_code=201)
def register(body: Registration, db: DbSession = Depends(get_db)) -> JSONResponse:
    if (
        body.redirect_uris != [CALLBACK]
        or body.token_endpoint_auth_method != "none"
        or set(body.grant_types) - {"authorization_code", "refresh_token"}
        or body.response_types != ["code"]
    ):
        raise oauth_error("invalid_client_metadata", "Chỉ hỗ trợ kết nối ChatGPT với callback đã cho phép")
    client = McpClient(id=new_session_token(), redirect_uri=CALLBACK)
    db.add(client)
    db.commit()
    return JSONResponse(
        {
            "client_id": client.id,
            "client_name": "ChatGPT",
            "redirect_uris": [CALLBACK],
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
    if (
        client is None
        or query.get("redirect_uri") != client.redirect_uri
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
        return page(
            "Đăng nhập để kết nối ChatGPT",
            "<p>Mở Reels Studio để đăng nhập hoặc đổi mật khẩu, rồi quay lại trang này.</p>"
            '<a href="/login" target="_blank" rel="noopener">Mở trang đăng nhập</a>'
            f'<p><a href="{escape(resource + "/oauth/authorize?" + str(request.query_params), quote=True)}">'
            "Tôi đã đăng nhập, tiếp tục</a></p>",
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
            expires_at=now() + timedelta(minutes=10),
        )
    )
    db.commit()
    return RedirectResponse(
        resource.removesuffix("/api/mcp") + "/chatgpt#" + urlencode({"ticket": ticket}),
        status_code=303,
        headers=PRIVATE_HEADERS,
    )


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
    return JSONResponse({"email": me.user.email, "scopes": auth.scopes.split()}, headers=PRIVATE_HEADERS)


def callback(client: McpClient, state: str, **values) -> RedirectResponse:
    params = {"state": state, "iss": require_enabled() + "/oauth", **values}
    return RedirectResponse(client.redirect_uri + "?" + urlencode(params), status_code=303, headers=PRIVATE_HEADERS)


@router.post(PREFIX + "/consent")
def consent(
    ticket: str = Form(max_length=128),
    decision: str = Form(max_length=10),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> RedirectResponse:
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
    client = db.get(McpClient, auth.client_id)
    if decision != "allow":
        state = auth.state
        db.delete(auth)
        db.commit()
        return callback(client, state, error="access_denied")
    code = new_session_token()
    auth.code_hash, auth.expires_at = hash_session_token(code), now() + timedelta(minutes=2)
    db.commit()
    return callback(client, auth.state, code=code)


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
            or redirect_uri != client.redirect_uri
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
        {"id": row.id, "scopes": row.scopes, "expires_at": row.expires_at.isoformat()}
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
    return RedirectResponse("/chatgpt", status_code=303, headers=PRIVATE_HEADERS)
