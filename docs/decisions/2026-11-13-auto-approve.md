# 2026-11-13 — "Tự duyệt": a member's finished renders approve themselves

Asked by namtc, 2026-11-13: "thêm một tính năng bật/tắt auto duyệt cho tất cả video". The owner chose, when the
conflict below was put to him: each member switches it for their own videos, it acts right after the render is
done, and only when there is no warning, with Muse telling the member on WhatsApp.

- **What:** a switch "Tự duyệt khi render xong" (above the video list of a topic group; `users.auto_approve`, off by
  default, `GET/PUT /api/me/auto-approve`). When a render job finishes (the worker's or a render machine's), and the
  switch of the video's maker is on, `auto_approve.settle` does what the maker's "Duyệt" button does: it calls the same
  `publish` (so every rule of "Đăng" holds: fresh MP4, schedule window, Page owner, logo/brand match, not already on
  that Page) with the plan idea's suggested time on the maker's own Page of the video's group (else their only Page).
- **Only when nothing needs a look:** a plan time that is still ahead, a Page, no warning from the script checks
  ("Ảnh cần ghi nguồn", banned words, length...), and an MP4 QC that passed. Anything else leaves the video for a
  manual "Duyệt". A video with a pending post is left alone.
- **Telling the member:** the app has no way to push to WhatsApp, so each result (`approved` or `held`, with the
  reason, Page and time) is kept in `auto_approvals`, and the MCP tool "Xem kết quả tự duyệt" (read-only, `after_id`
  cursor) gives a member's new results to Muse, which messages them. Muse's routine: call it every few minutes with the
  last `id` it reported, message the member one line per result, keep the largest `id`.
- **Conflicts:** it relaxes "Approval stays a manual gate per idea; nothing is scheduled without a member's tap" of
  [2026-11-12 — "Duyệt" on the plan tab](2026-11-12-plan-approve-button.md), only for a member who turned the switch on
  and for a clean video. It does not bring back "Bán tự động" (removed 2026-11-12): nothing is made by itself, only
  approved. A video upgraded by "Nâng cấp video chưa đăng" still has its page-queue approval withdrawn; it is
  approved only when it is rendered again, if the switch is on.
- **Cost of a wrong yes:** a clean-looking video can still show a wrong picture; nobody watched it. The member can
  cancel the post ("Hủy đăng") up to its time, and Muse's message is the reminder.
