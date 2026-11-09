# 2026-11-09 — An MCP connection ends 30 days after its last refresh, not 30 days after it was granted

Brief [docs/specs/mcp-connection-sliding-expiry](../specs/mcp-connection-sliding-expiry/brief.md), chosen by the owner
(namtc) on the morning of 2026-11-09. Replaces, in "2026-11-03 — ChatGPT controls drafts through private MCP and
member-authorized OAuth" of [decisions.md](../decisions.md), "Connections last at most 30 days" (and the same words
repeated in the later MCP entries): every connection, used daily or not, died exactly 30 days after the member's
consent and had to be approved again, while the daily build runs through one (the Muse connection approved on
2026-11-08 would have died around 2026-12-08).

- **Sliding**: a successful refresh sets the connection's end to now + 30 days (`CONNECTION_LIFETIME`), in the
  refresh branch of the token endpoint ([routes_mcp.py](../../api/src/reels_api/routes_mcp.py)), after its checks
  pass. Not in `rotate_tokens`, which the first grant also calls, so the grant keeps its own code unchanged. The new
  access token then gets its full hour.
- **Unused for 30 days, it ends**: an ended connection's refresh is refused as before; a refresh never revives it.
  Tokens are not made endless, as the owner weighed and declined.
- **Connections granted before** slide from their first refresh after the deploy, with no data migration and no new
  consent.
- **Unchanged**: one-hour access tokens, rotating both tokens, the scopes, the callback allowlist, revoking, and the
  binding to the member's login session: signing out everywhere, changing the password or disabling the member still
  ends the connection at once, and a session that expires ends it too. Refreshing does not extend that session.
