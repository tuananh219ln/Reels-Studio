# 2026-11-18 — "Bình luận" on "Bài đăng" shows where each reel's comments stand

Asked by tuananh219ln ("phải làm bảng theo dõi để biết"): after saving detailed comments nobody could tell which
reel had them up, which was waiting, or when the rest would go up.

- A third view of "Bài đăng", "Bình luận" (`/posts?view=comments`, `GET /api/posts/comments`), next to "Danh sách"
  and "Lịch", not a new page or menu item. Read only: no button asks the worker; "Bình luận ngay" stays on the video.
- Scope is the reels live on Facebook within 3 days, the same window as the detailed comments
  ([2026-11-18-comment-pacing](2026-11-18-comment-pacing.md)).
- "Dự kiến lên đủ" is an estimate from the pacing (average rest, a minute between videos, one a day after the first 24 hours, 100 a Page a day), not a
  promise; the worker keeps its own random rests.
- Comments the worker writes and the count per Page come from what the app already stores; no migration.
