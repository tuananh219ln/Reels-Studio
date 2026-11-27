# Exact-time scheduling through MCP for an already-approved video

Written by Muse, 2026-11-26. Code checked on main (HEAD d79713c, PR #362).

## Context

- `approve_video` (`api/src/reels_api/mcp_server.py:598`) has `publish: "schedule"`
  with `schedule_at` (a datetime with timezone) — but `review.approve`
  (`api/src/reels_api/review.py:118`) refuses any video that is not pending
  (`409 not_pending`, "Video đã được duyệt rồi"). Exact-time scheduling through MCP
  only works for a video that is still waiting for review.
- `schedule_video` (`mcp_server.py:2499`) takes only `video_id` + `fanpage_id` and
  calls `routes_queue.add`, which puts the video in the Page's queue; the worker
  fills it at the Page's next free slot (`page_queue.fill`, `FILL_LEAD` 30 minutes,
  `FILL_AHEAD` 48 hours, `page_queue.py:33-35,119-135`). There is no way to pick
  the time.
- The web can pick an exact time: `ApproveVideoButton` approves through
  `/review/{id}/approve` and then calls `POST /videos/{id}/publish` with
  `scheduled_at` (`web/src/components/actions/ApproveVideoButton.tsx`).

Consequence: an already-approved video (a clone approved yesterday, a FoodDose reel
approved at 14:00) can only be scheduled at an exact slot through the browser.
The Threads 07:30 scheduling job also uses the browser for this reason (plus the
tool's Threads `post_times` are 11:30/18:00/21:00 while the contest slots are
12:00/18:00/21:00).

## Scope

Let MCP schedule an already-approved video at an exact time. Implement exactly
ONE of the two options below — the coder picks the smaller change and records
the choice in a decision doc:

(a) Optional `scheduled_at` on `schedule_video`: when present, create the
    Publication at that time (the same path the web publish route takes) instead
    of going through the queue fill; when absent, keep the current behaviour.
    Validate: the time must be one of the Page's posting times
    (`page_queue.post_times`) and a free slot (`page_queue.free_slots`), within
    the next 48 hours; otherwise `409` naming the reason. Still call
    `review.ensure_approved` first (an unapproved video → `409 not_approved`,
    unchanged).
(b) Let `approve_video(publish="schedule")` accept an already-approved video:
    skip the approval step when `approved_signature` still matches the current
    MP4 (`review.publish_blocker` returns None) and only schedule — i.e. make
    approve idempotent for an approved video.

## Out of scope

- Scheduling more than 48 hours ahead through MCP (the web dialog can; a later slice).
- Changing `post_times` through MCP (already possible via `PATCH /api/queue/pages/{id}`).
- Auto-approving through a job: a scheduling job may only schedule videos a member
  already approved; it must never approve on the member's behalf.

## Acceptance

1. An approved video + MCP + an exact free slot (e.g. 18:00) → a Publication with
   `scheduled_at` exactly at that time, on the right Page.
2. An exact slot already taken by another post → `409`, naming the conflict.
3. A time that is not one of the Page's posting times → `409`.
4. An unapproved video → `409 not_approved` (unchanged).
5. No time given → the old behaviour (next free slot).
6. MCP tests like `api/tests/test_mcp_duplicate_schedule.py`.

## Note

Once this lands, the Threads 07:30 scheduling job can drop the browser and use
MCP alone. That is a job-body change, not part of this brief, and it needs the
member's explicit agreement before any job approves videos through MCP.
