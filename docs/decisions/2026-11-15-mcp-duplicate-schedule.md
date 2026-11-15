# 2026-11-15 — MCP copies a video and adds it to a Page's queue

Asked by the owner (namtc), brief [docs/specs/mcp-duplicate-schedule](../specs/mcp-duplicate-schedule/brief.md):
copy the ten best videos of one Page to a new Page and post four a day, from the assistant rather than by hand.

- **Two MCP tools, the web's rules:** `duplicate_video` is "Nhân bản y hệt" ([2026-11-14](2026-11-14-duplicate-video.md))
  and `schedule_video` is "Thêm vào hàng chờ". Neither has a rule of its own.
- **The copy takes the target Page's logo** (owner's choice, 2026-11-15): moving a video to another group keeps its
  channel and logo, so a copy of a video with the old Page's logo would be refused by the new Page's queue.
  `fanpage_id` switches the copy to the channel linked to that Page, with its logo on, through the video page's own
  check (the member's own channel, with a logo).
- **Relaxes "MCP has no posting tool"** of [2026-11-09 — Only a Page's owner posts to it](2026-11-09-page-owner-posts.md):
  `schedule_video` is the first MCP tool that leads to a Facebook post. It still only adds to the member's own
  Page's queue; the time is the queue's, and the post is made by the worker as for the web's button. The server's
  instructions ask the assistant to queue only when the member asks, after looking at the render. Posting at once,
  picking a time, deleting a video or changing an account stay out of MCP.
