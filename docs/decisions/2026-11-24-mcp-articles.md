# 2026-11-24 — MCP gets article tools, and a `reels:publish` scope to post them

Asked by the owner (namtc): an assistant should make an article (caption, hashtags, photos, "Thẻ chữ"), then post it
now or at a time on the member's own Page, and take a scheduled one back.

- **Nine tools, the web's routes:** list, read, create, edit, add a photo (link or library), text card, delete, and
  `publish_article` / `unschedule_article`. They call `routes_articles` functions, so there is no rule of their own
  (checks, "never posted twice", the 15-minute-to-29-day window, the Page's owner, locks, the `publish` job).
- **Relaxes** "Posting at once, picking a time, deleting a video or changing an account stay out of MCP" of
  [2026-11-15 — MCP copies a video and adds it to a Page's queue](2026-11-15-mcp-duplicate-schedule.md): for
  *articles*, posting at once and picking a time are now allowed. Videos are unchanged (queue only), and deleting a
  video or changing an account stays out. Deleting an *article draft* is allowed (not a posted or scheduled one).
- **A new scope, `reels:publish`,** instead of widening `reels:write`: a member who connected an assistant to edit
  keeps exactly that. The two posting tools need it; the consent screen names it ("Quyền đăng bài lên Page") and drops
  "không được đăng bài" when it is asked. Existing connections do not have it and must reconnect.
- **No AI cost:** the assistant writes the caption itself; the AI photo and the AI caption buttons are not tools.
- **Asked of the assistant, not enforced:** post only when the member asks, after they saw the caption and photos
  (the server's instructions), as for `schedule_video`.
