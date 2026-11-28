# 2026-11-28 — Many videos ticked and deleted at once on the Video list; "Nhân bản" leaves the video menu

From the owner's spec "Chọn nhiều video & xóa hàng loạt" (2026-11-28). The spec left four questions open; the owner
answered them before the work.

- **Deleted for good, no trash**: the same deletion as `DELETE /api/videos/{id}` (rows, then the files). The spec's
  trash with 30 days, restore and "Hoàn tác" is left for later: it needs `deleted_at` filtered in about 37 modules
  that read videos (worker, Telegram, MCP, stats, plans). The dialog says it cannot be undone.
- **Only the maker deletes** ([2026-11-09](2026-11-09-delete-by-maker.md) stands; no admin exception). A teammate's
  video, or one holding a teammate's post, note or queue place, is skipped as `forbidden`.
- **Skipped, never deleted**: a video **posted** on any platform (`published`, kept for the view report) and one a job
  holds (`rendering`). The check is on the server for every id. `DELETE /api/videos/{id}` is unchanged; only the menu's
  "Xóa video" is greyed out (with the reason) for those two cases.
- **Type the number from 20 videos** (the spec said 10 in one place, 20 in another), and always after "Chọn tất cả N
  video khớp bộ lọc".
- **The web sends ids, not a filter**: the Video list is filtered in the browser, so "all that match" is the ids it
  shows. `POST /api/video-bulk/delete` and `/delete/preview` take up to 500 ids (the web sends longer choices in
  parts), delete one video per transaction and answer `deleted` and `skipped` with a reason.
- **Selection** is kept across pages, sorting and the Bảng/Thẻ switch, and cleared by any filter or search change.
  There is no "Cột" view on this list, so nothing to hide there.
- **Not done**: the "Xem" link that highlights skipped rows (they stay ticked instead).
- **"Nhân bản" is gone from the "⋮" menu and the video page's "⋯"**, leaving "Nhân bản y hệt" and "Nhân bản xáo
  cảnh". The API and the clone job stay (TikTok version, MCP and "Bài đăng" still use them).
