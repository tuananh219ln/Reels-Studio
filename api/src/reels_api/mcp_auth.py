"""OAuth credentials stay in Postgres as hashes and are bound to an existing member session."""

import base64
import hashlib
import re
from datetime import timedelta
from urllib.parse import urlsplit

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import config
from .errors import ApiError
from .models import McpConnection, Session, User
from .security import hash_session_token, new_session_token
from .sessions import now

SCOPES = {"reels:read", "reels:write"}
ACCESS_LIFETIME = timedelta(hours=1)
CONNECTION_LIFETIME = timedelta(days=30)
# The callbacks of the AI apps a member may connect; no arbitrary redirect hosts or fetches. Issuer identification
# makes ChatGPT's stable. Claude's hosted apps (web, Desktop, mobile) share one, which may move to claude.com.
CHATGPT_CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"
CLAUDE_CALLBACKS = ("https://claude.ai/api/mcp/auth_callback", "https://claude.com/api/mcp/auth_callback")
HOSTED_CALLBACKS = frozenset({CHATGPT_CALLBACK, *CLAUDE_CALLBACKS})
# Claude Code is a native client: an RFC 8252 loopback redirect on a port that changes every session.
LOOPBACK = re.compile(r"http://(localhost|127\.0\.0\.1)(?::(\d{1,5}))?/callback")
MAX_REDIRECTS = 4
SERVER_POST_PATHS = frozenset({"/api/mcp", "/api/mcp/oauth/register", "/api/mcp/oauth/token", "/api/mcp/oauth/revoke"})


def public_url() -> str:
    raw = config.read_env("MCP_PUBLIC_URL").rstrip("/")
    if not raw:
        return ""
    parsed = urlsplit(raw)
    local = parsed.hostname in {"localhost", "127.0.0.1"}
    if (
        parsed.scheme not in ({"http", "https"} if local else {"https"})
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path != "/api/mcp"
        or parsed.query
        or parsed.fragment
        or f"{parsed.scheme}://{parsed.netloc}" not in config.allowed_origins()
    ):
        raise config.ConfigError("MCP_PUBLIC_URL phải là https://<tên-miền-web>/api/mcp trên ALLOWED_ORIGINS")
    return raw


def require_enabled() -> str:
    url = public_url()
    if not url:
        raise ApiError(404, "mcp_disabled", "Chưa bật kết nối ChatGPT / Claude")
    return url


def _loopback(uri: str) -> tuple[str, str] | None:
    """(host, port) of a loopback callback, or None."""
    found = LOOPBACK.fullmatch(uri)
    if found is None or (found.group(2) and not 0 < int(found.group(2)) < 65536):
        return None
    return found.group(1), found.group(2) or ""


def allowed_redirect(uri: str) -> bool:
    return uri in HOSTED_CALLBACKS or _loopback(uri) is not None


def registered(redirects: str) -> list[str]:
    """The callbacks a client registered, stored space-separated (a URI holds no space)."""
    return redirects.split()


def redirect_matches(redirects: str, uri: str) -> bool:
    """`uri` is one the client registered; a loopback one matches whatever its port (RFC 8252 section 7.3)."""
    if uri in registered(redirects):
        return True
    asked = _loopback(uri)
    return asked is not None and any(
        (known := _loopback(one)) is not None and known[0] == asked[0] for one in registered(redirects)
    )


def app_of(redirect: str) -> str:
    """Which app a callback belongs to, named on the consent page and in the member's connections."""
    if redirect == CHATGPT_CALLBACK:
        return "ChatGPT"
    if redirect in CLAUDE_CALLBACKS:
        return "Claude"
    return "Claude Code"


class OAuthError(ApiError):
    pass


async def oauth_error_handler(request: Request, exc: OAuthError) -> JSONResponse:
    return JSONResponse(
        {"error": exc.code, "error_description": exc.message},
        status_code=exc.status,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def oauth_error(code: str = "invalid_grant", message: str = "Quyền kết nối không hợp lệ hoặc đã hết hạn") -> OAuthError:
    return OAuthError(400, code, message)


def pkce(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def valid_verifier(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", value) is not None


def member_session(db: DbSession, session_id: int) -> Session | None:
    session = db.scalar(select(Session).where(Session.id == session_id).execution_options(populate_existing=True))
    if session is None or session.expires_at <= now():
        return None
    user = db.scalar(select(User).where(User.id == session.user_id).execution_options(populate_existing=True))
    if user is None or not user.is_active or user.must_change_password:
        return None
    return session


def connection_for(db: DbSession, token: str) -> tuple[McpConnection, Session] | None:
    connection = db.scalar(
        select(McpConnection)
        .where(McpConnection.access_hash == hash_session_token(token))
        .execution_options(populate_existing=True)
    )
    if (
        connection is None
        or connection.resource != public_url()
        or min(connection.access_expires_at, connection.expires_at) <= now()
    ):
        return None
    session = member_session(db, connection.session_id)
    return (connection, session) if session else None


def rotate_tokens(connection: McpConnection) -> dict:
    access, refresh = new_session_token(), new_session_token()
    connection.access_hash, connection.refresh_hash = hash_session_token(access), hash_session_token(refresh)
    connection.access_expires_at = min(now() + ACCESS_LIFETIME, connection.expires_at)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": max(0, int((connection.access_expires_at - now()).total_seconds())),
        "scope": connection.scopes,
    }


# The router's dependency runs before cookie authentication, keeping the integration off when unset.
Enabled = Depends(require_enabled)
