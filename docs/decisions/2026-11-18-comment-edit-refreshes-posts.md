# 2026-11-18 — Editing a video's comments updates its live posts by itself

Asked by tuananh219ln ("tự động cập nhật"): "Bình luận thêm" typed on a video whose post already had its first
comment stayed off Facebook until a member pressed "Cập nhật bình luận".

- `PATCH /api/videos/{id}` that changes the pinned comment or "Bình luận thêm" sets `comment_requested_at` on each
  live Facebook post of the video that already has a comment (`post_comments.ask_after_edit`). The existing worker
  round then edits or writes them, with the usual pacing and day cap; no new Facebook call.
- Left alone: a post never commented (it still waits for "Tự bình luận" or "Bình luận ngay"), a video marked
  "Đã dán link tay", and a post resting before its run's next comment (its later time is kept).
- A pinned comment that changes only because the scenes changed (the template, 2026-11-14) does not ask; the next
  attempt of any kind writes the current text.
