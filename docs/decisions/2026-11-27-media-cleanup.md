# 2026-11-27 — The app deletes a posted video's media files after 30 days (the video and its numbers stay)

From [docs/specs/video-media-retention](../specs/video-media-retention/brief.md). The owner chose "Đồng ý hết đề xuất"
on 2026-11-27 after `storage-report` showed 28.4 GB for 367 videos, +1.1 GB a day, on a 96 GB disk with 37 GB free.

- **An exception to "only the maker deletes"** ([2026-11-09](2026-11-09-delete-by-maker.md)): the worker deletes the
  media files of any member's video by itself. It deletes files only, never a video or a database row, and anyone
  can press "Giữ media" to keep a video's files.
- **Level 1 first**: 30 days after a video's last live post the worker deletes everything in its folder except the
  MP4s and the thumbnail, so posting again, the board and the lists keep working. Deleting the MP4 after 60 days
  (level 2) is left for later.
- **Which videos**: approved, with a live post, no post still to go out (pending, scheduled, waiting for a link), not
  in a Page's queue, no job, nobody editing it, not marked "Giữ media". A post left private on YouTube does not hold a
  video back: level 1 keeps the MP4, and without this such a video would never be cleaned. Never-posted videos are
  not touched.
- **Winners stay**: a video with a Facebook post at 3 times its Page's median 48-hour views or more (the "winner"
  mark is 10 times), or the source of a shuffled or TikTok copy made within the last 30 days.
- **Deleted for good**: no backup of the files; a cleaned video says so and cannot be rendered, duplicated or
  shuffled (its script, scenes and numbers stay). "Nhân bản" by AI still works.
- **Off until the owner turns it on**: `MEDIA_CLEANUP_ENABLED`, days in `MEDIA_CLEANUP_DAYS` (30). The warning three
  days before (web, private Telegram) ships before the switch is turned on.
