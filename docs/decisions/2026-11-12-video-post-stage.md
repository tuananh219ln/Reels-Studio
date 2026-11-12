# 2026-11-12 — A rendered video is named by its posting: "Chờ đăng", "Đã lên lịch", "Đã đăng"

The owner (namtc), 2026-11-12: a group's status filter offered only "Xong", which said nothing about whether the
videos were out.

- **The api names it** (`videos.post_stage`, `status_label`): a video with its MP4 and no job is "Chờ đăng" (no post),
  "Đã lên lịch" (a Facebook post set for later) or "Đã đăng" (out on any platform). The machine code stays `done`,
  with `post_stage` (`ready`, `scheduled`, `posted`, null before an MP4), so nothing reading `status` changes.
- **One list of choices** (`web/src/lib/videoStatus.ts`) for the video list and a group's "Video" tab: Nháp, Đang xử
  lý, Chờ đăng, Đã lên lịch, Đã đăng, Lỗi, MP4 cần render lại, every one listed with its count even when empty.
- A plan idea whose video has an MP4 and no post is "Chờ đăng" too, not "Xong". Nhật ký job keeps "Xong", which is
  a job's.
