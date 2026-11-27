# 2026-11-27 — The queue respects the plan; the time is shown before it is chosen

Asked by namtc after video 78 (no plan idea) was approved on Telegram and pressed into the Page's queue: it took
tomorrow 07:00, a time meant for the plan's video, and nothing said which time the queue would give.

- **Queue and plan.** A plan idea whose video is not yet scheduled on the Page holds its posting time (the idea's day
  and place, in the group's zone) against every other video of the Page's queue, until 2 hours before that time
  (`page_queue.plan_held`, `PLAN_RELEASE`). A video of that idea takes its own time when free; any other video takes the
  next free time no idea holds. A hold only counts when it is exactly one of the Page's free times (a Page with times
  of its own may not match the group's). When every free time is held the video stays in the queue with the reason.
  This is the old "the idea's time, taken: the next free" of 2026-11-08 (removed 2026-11-12 with the semi-automatic
  round) in the queue, not a new kind of reservation: nothing is stored, a plan that changes releases its time at once.
- **Two posts at one time need a second yes.** `POST /videos/{id}/publish` answers 409 `slot_taken` when another video's
  open post of the Page is within 30 minutes of the time asked; "Vẫn hẹn" (`allow_overlap`) sends it again. This
  covers the web drawer, the plan tab's "Duyệt", "Tự duyệt" (held, with the reason) and MCP `schedule_video_at`.
- **The time is shown before the press.** After "Duyệt" on Telegram the message says the next free time of each Page
  and, for a video with a plan idea, a "📅 Đăng lúc ..." button (`qp:`) that posts at the idea's time as the plan tab's
  "Duyệt" does; "Thêm vào hàng chờ" in the app shows the same time (`GET /queue/videos/{id}` `next`).
- **Not done (asked, next PRs):** splitting "Duyệt" from scheduling on every channel (P4 of the analysis), a visible
  "Đã duyệt, chưa hẹn giờ" list.
