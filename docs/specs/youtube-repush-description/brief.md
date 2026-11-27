# Re-push a YouTube description from the group meta (after a hand edit in Studio)

Written by Muse, 2026-11-26. Code checked on main (HEAD d79713c, PR #362).

## Context

- Both YouTube upload paths build the description at upload start from the video's
  caption plus the group's "Mô tả YouTube" (`youtube_publish.py:49-55`,
  `_description_and_tags`; `youtube_meta.py:103`). The built description is stored as
  `post.post_text` before the file is sent (`youtube_publish.py:92`). The manual
  button (`routes_youtube.py`) only creates a pending Publication + Job; the
  description is built when the session opens.
- A hand edit inside YouTube Studio is outside the tool: nothing pushes the code
  version back. 26/11: V413's description was overwritten by a manual job, restored
  by hand-paste; 25 old Threads Shorts were upgraded by hand (13:15–13:32). The
  standing rule is now "when group meta is set, do NOT hand-edit descriptions" —
  but a hand edit can still happen, and today the only fix is another hand edit.
- The uploaded video's YouTube id is stored: `Publication.external_id` + `post_url`
  (`youtube_publish.py:97-98`, `post.external_id, post.post_url = video_id,
  youtube_upload.shorts_url(video_id)`).
- Scope: `youtube_upload.py:28` requests
  `SCOPES = ("https://www.googleapis.com/auth/youtube.upload",
  "https://www.googleapis.com/auth/youtube.readonly")`. The YouTube Data API
  `videos.update` call needs the `youtube.upload` scope — already granted with the
  existing connection, so no new OAuth consent is needed. Reuse the existing
  connection token. Caveat, same as uploads: the Google refresh token expires every
  7 days (app in testing mode), so a stale token must fail with a clear
  "reconnect" error, never a silent no-op.

## Scope

Add one action that pushes the code-built description (and tags) to an already
uploaded YouTube Shorts, without re-uploading the MP4:

- A service function that, for a video with a YouTube Publication
  (`platform='youtube'`, `external_id` set): rebuilds description + tags with the
  SAME functions as the upload (`_description_and_tags` with the CURRENT caption
  + CURRENT group `youtube_meta`; title via `youtube_upload.metadata()`, exactly
  as the upload does), then calls `videos.update` with that snippet.
- A "Đẩy lại mô tả" button on the video detail page (YouTube publication row):
  shows the rebuilt description for confirmation before sending, then reports
  success or the error.
- An MCP tool with `video_id` calling the same service, so Muse can re-push after
  checking the group meta (same approval rule as other writes: only when the
  member asks).
- After a successful push, update `post.post_text` to the new description (so the
  tool's record matches YouTube again) and record the re-push (who/when) in
  `video_events` or the job log.
- Refuse with a clear reason when: no YouTube upload exists yet for the video
  (no `external_id`), or the group's `youtube_meta` is not set (there is nothing
  to push from).

## Out of scope

- Re-uploading the MP4, changing the thumbnail, or touching privacy status.
- Re-pushing tags-only or title-only separately (the snippet goes as one unit, as
  the upload does).
- Bulk re-push (one video at a time in this slice; the 25-video case was a
  one-off). Auto-detecting Studio edits (no polling — the member presses the
  button when they notice a mismatch).
- Videos whose group meta is not set (refuse; do not invent a description).

## Acceptance

1. V413 (or any uploaded Shorts whose Studio description was hand-edited) →
   re-push → the YouTube description equals the code version (OP verbatim + CTA
   + 12 hashtags) and the Tags field equals the code tags.
2. `post.post_text` matches the new description; the re-push is recorded
   (who/when).
3. A video with no YouTube upload yet → clear refusal, nothing sent.
4. Group meta not set → clear refusal, nothing sent.
5. Stale Google token → clear "reconnect" error (same as upload failures).
6. No MP4 re-upload: the YouTube video id and published date are unchanged.
7. Tests like `api/tests/test_youtube*.py` (mock the `videos.update` call).

## Risk

`videos.update` replaces the whole snippet — a wrong rebuild would overwrite a
 good hand edit. Mitigated by rebuilding with the exact upload functions and
 showing the rebuilt description for confirmation on the web before sending.
