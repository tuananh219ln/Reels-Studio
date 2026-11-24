# 2026-11-24 — Files reach the library through public links, Google Drive included, not through MCP uploads

An assistant (Muse, ChatGPT, Claude) cannot send a file over MCP: the server takes requests of 128 KB at most
(`max_request_body_size`), which leaves about 95 KB for a base64 photo, and "MCP does not carry files" stands. So a
photo or clip an assistant makes reaches "Kho tư liệu" through `add_media_from_links`, which the server downloads
itself with the web upload's limits (photo 15 MB, clip 50 MB, a clip over a minute keeps its first minute).

- A link to one **Google Drive** file shared "anyone with the link" is accepted: `remote_media.normalize_link` turns
  `/file/d/<id>/view`, `open?id=` and `uc?id=` into `drive.usercontent.google.com/download?id=<id>&export=download`
  (the `resourcekey` is kept). The member's original link stays as the item's source. A Drive folder or a Google
  document is refused. No Drive OAuth, no stored secret: only public links. Drive stops scanning files over about
  100 MB, well above both limits, so its virus-warning page is not expected; if Drive still answers with a page,
  the failure says the link is not public.
- `add_media_from_links` takes `tags` (30 at most, 50 characters each, as everywhere), passed to `add_links`.
- Each entry of `failed` carries a `reason` (`not_public`, `expired_or_unreachable`, `too_large`, `not_media`,
  `blocked_host`, `invalid_link`) next to the message, so the assistant picks the next step itself: another link
  (Drive after the assistant's own file link), a fresh link, a smaller file, and at most two tries per photo before it
  tells the member to upload in the browser.

Not decided here: Drive OAuth or folder links, a base64 upload tool, a bigger MCP request limit.
