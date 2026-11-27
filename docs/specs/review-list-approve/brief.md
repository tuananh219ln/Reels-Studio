# Approve (+ queue) from the video list — extend the review gate (PR #362)

Written by Muse, 2026-11-26. Code checked on main (HEAD d79713c, PR #362 merged 2026-11-26 15:16).

## Context

PR #362 added a review gate (`api/src/reels_api/review.py`): every video starts
`pending_review`; every route that schedules or posts refuses an unapproved video
(`409 not_approved`, `review.ensure_approved`); a new render sends the video back
to `pending_review` and withdraws its queue item and unposted posts. One service
serves the web, MCP and "Tự duyệt", so the channels cannot disagree
(`docs/decisions/2026-11-26-review-gate.md`).

The web got the gate in two places:

- The video detail page's "Đăng bài" tab: `ReviewCard`
  (`web/src/components/video/ReviewCard.tsx`, used in `PublishTab.tsx:62`) — shows
  status, blockers/warns, "✓ Duyệt" (asks "Vẫn duyệt" when warnings remain,
  `acknowledge_qc: true`), "Bỏ video", "Khôi phục".
- The plan tab and the detail page's status card: `ApproveVideoButton`
  (`web/src/components/actions/ApproveVideoButton.tsx`, used in `PlanTab.tsx:1502`,
  `StatusCard.tsx:211`, `VideoActions.tsx:168,200`) — approves first (warnings shown
  in the confirmation), then publishes/schedules exactly as before.

The video list has no approve action. `videoList/VideoCard.tsx` and `cells.tsx`
only show the status label: after #362 a rendered unapproved video reads
"Chờ duyệt" instead of "Chờ đăng" (`web/src/lib/videoStatus.ts`: `needsReview`,
`videoStatusLabel`; `VideoRow.review_status`, `review_label` in
`web/src/lib/api.ts:101`). Approving means opening every video's detail page.

## Problem

The daily flow approves 3 videos per page (6 Threads videos, 4 clones, 2 FoodDose
reels). Each approval costs two steps (open detail page, then approve) instead of
one, and the list — where the member already sees what is waiting — cannot act.

## Scope

Add to every video row in the video list (`videoList/VideoCard.tsx`, `cells.tsx`):

- A "Duyệt" button when `needsReview(row)` is true: approve only, exactly like
  `ReviewCard` (POST `/review/{id}/approve`).
- A "Duyệt + vào hàng chờ" button: approve, then add to the Page's queue
  (POST `/api/queue`), exactly like MCP `approve_video` with `publish: "queue"`.
- Both buttons reuse the same rules as `ReviewCard`/`ApproveVideoButton`:
  blockers disable the buttons and show the reason; warnings are listed in a
  confirmation ("Vẫn duyệt") and only then sent with `acknowledge_qc: true`;
  disabled while the video is locked or a render is running.
- Reuse `review.py` through the existing `/api/review` routes — no second approval
  path. Reuse `ApproveVideoButton`'s confirmation where possible instead of a new
  component.

## Out of scope

- Bulk approve (approve many at once) — a later slice if the member asks.
- Any change to `ReviewCard`, `ApproveVideoButton`, `review.py`, or the gate rules.
- Telegram / email / web push reminders (later slices of the original spec).

## Acceptance

1. A pending video approved from the list → `review_status` approved, a
   `video_events` row records the approval via web, and the row label changes
   from "Chờ duyệt" to "Chờ đăng".
2. "Duyệt + vào hàng chờ" → approved AND a `PageQueueItem` exists; the worker
   schedules it at the Page's next free slot.
3. A video with warnings (e.g. loudness fail) → clicking Duyệt shows the
   confirmation listing every warning; "Vẫn duyệt" sends `acknowledge_qc: true`.
4. A video with a blocker → the buttons are disabled and the reason is shown.
5. Approved, scheduled, posted, rejected, locked, or rendering videos show no
   approve buttons.
6. e2e coverage like `web/e2e/queue.spec.ts` / `videos.spec.ts` (extended in #362).

## Risk

Approving from the list without watching the MP4 — mitigated by showing the
button only for rendered videos and keeping the warning confirmation. No bulk
approve in this slice, so one wrong tap costs one video, not a batch.
