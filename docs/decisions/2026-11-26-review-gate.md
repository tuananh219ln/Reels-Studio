# 2026-11-26 — A review gate: nothing is scheduled or posted until a member approves the MP4

Asked by the owner (namtc), from the spec "Luồng duyệt video Muse & tối ưu màn chi tiết video" (26/11/2026), whose
first slice this is. Chosen with the owner: build the gate now (the spec's GĐ1 without versions, remix, beats and
Telegram), let Muse post through MCP with the existing `reels:publish` scope, and leave the push channel for later.

- **A gate stored on the video, in the backend.** `videos.review_status` is `pending_review` (every video starts
  there, and every render goes back to it), `approved` or `rejected`, with who approved, when, through which channel
  (`web`, `muse_chat`, `auto`, `legacy`) and the MP4's fingerprint at that moment (`approved_signature`). "Scheduled"
  and "published" are not stored: they are read from the video's posts, as before. Every step is a `video_events` row.
  One service, [review.py](../../api/src/reels_api/review.py), is called by the web (`/api/review`), by Muse (MCP) and
  by "Tự duyệt", so the channels cannot disagree.
- **Every route that schedules or posts refuses an unapproved video** (`409 not_approved`): Facebook "Đăng", Instagram,
  TikTok's API, YouTube upload, and a Page's queue. A post made by hand and recorded afterwards is not a posting, so it
  is not gated. The posting jobs (`publish`, `tiktok_publish`, `ig_publish`, `youtube_publish`) check again right before
  they start and fail with the same words (the spec's R3), keeping a `publish_skipped` event: a rejection or a
  re-render may have come after the job was queued. An approval holds only for the MP4 it was given for.
- **A new MP4 goes back to review and withdraws what was planned for the old one** (R2), at the end of a render (the
  worker's and a render machine's): the video is `pending_review` again, its Page-queue item is removed, posts that
  never reached a platform are cancelled, and a Facebook post already scheduled there gets an `unpublish` job (the first
  one only: a video has one active job at a time). "Tự duyệt" then approves the new MP4 again for a member who turned it
  on, as before.
- **Approving asks for a finished, up-to-date render.** `blocker` items stop it (no or outdated MP4, an empty title, a
  script check that blocks rendering); `warn` items (the script's warnings, a failed MP4 QC) need `acknowledge_qc`, which
  the web sets with "Vẫn duyệt" and Muse only after the member confirmed each one.
- **Videos already scheduled or posted stay approved** (`legacy`, for the MP4 they have), answering the spec's open
  question 11.1 the less disruptive way: nothing already planned is held back. Every other video with an MP4 waits.
- **The existing "Duyệt" of the plan tab and "Tự duyệt" are the same act plus a schedule**: they approve, then post
  with the rules they had. This keeps "Approval stays a manual gate per idea" of
  [2026-11-12](2026-11-12-plan-approve-button.md) true and does not change [2026-11-13](2026-11-13-auto-approve.md),
  whose switch now also sets the approval.
- **Relaxes "Posting at once, picking a time … stay out of MCP"** of
  [2026-11-15](2026-11-15-mcp-duplicate-schedule.md) for videos, as [2026-11-24](2026-11-24-mcp-articles.md) did for
  articles: `approve_video` with `publish` `now` or `schedule` posts for real and needs the `reels:publish` scope
  (`queue` only adds to the Page's queue). Approving alone (`none`) needs only write. `get_pending_videos` and
  `reject_video` are the other two tools. Asked of the assistant, not enforced: approve only after the member agreed in
  the chat.
- **Not built here** (the spec's later slices): versions and "Muse làm bản khác", strategy and beats, the left column,
  Telegram, email and web push, the reminder, "tự đăng khi QC đạt" as a per-video flag, and a limit on remixes.
