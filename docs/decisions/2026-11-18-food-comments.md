# 2026-11-18 — A detailed comment per dish, written by the member's assistant over MCP

Asked by tuananh219ln: each dish of a posted video gets its own comment (benefit, how to make it, who should not eat
it), written from the video's own scenes, with Claude on the web rather than the team's API.

- Reuses `videos.extra_comments` and the comment worker (`post_comments._write_extras`), so ordering, edits by place and
  retries need no new code. `MAX_EXTRA_COMMENTS` goes from 5 to 12, since a list video has 7+ dishes.
- No AI call in the app: two MCP tools, `list_videos_for_food_comments` and `set_food_comments`. The server rejects
  cure promises and the group's banned words, as the pinned-comment work does ([2026-11-18-pinned-comments](2026-11-18-pinned-comments.md)).
- Scope is posts live within 7 days. Facebook cannot delete a comment through this app, so fewer comments than before
  leave the old ones on the Page.
- **Pacing (agreed with tuananh219ln):** the worker writes one comment per turn and the Page rests a random 30–60 s
  after the pinned/first comment, 45–90 s between the extras and 5 minutes after a video's last comment before another
  video's start; at most 100 comments a Page a day (Vietnam time), the rest waits for the next day. State is on `fanpages`
  (migration 0104, branched from 0102 because 0103 of PR #280 is not on main: the later PR to land re-points
  `down_revision`). The rest applies to every comment the worker writes under a reel, not only these.
