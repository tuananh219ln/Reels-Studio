# 2026-11-19 — An Instagram post cut off by a worker restart is queued again once

Asked by tuananh219ln, 2026-11-19 ([#305](https://github.com/tuananh219ln/Reels-Studio/issues/305)): a deploy restarted
the worker while an `ig_publish` job waited for Instagram to process the video, and the video showed "Đăng Instagram
lỗi: Worker khởi động lại giữa chừng" until a member pressed "Thử lại".

- **Narrows** "a dead worker's job is never re-run automatically" (2026-10-31) for `ig_publish` only, as
  [2026-11-15 article posting retries](2026-11-15-article-posting-retries.md) did for articles. The interrupted job still
  fails with the same reason; the restarted worker adds a new queued job for the same post (`retry_of_id` the old one,
  `params.after_restart`), as "Thử lại" would.
- **Why it is safe:** an Instagram post costs no AI money, and `ig_publish.py` already never posts twice (it saves
  `finish_sent_at` before publishing and, on a retry, asks Instagram about the container and looks for the Reel).
- **Once only:** a job queued by a restart and cut off by another restart stays failed and waits for "Thử lại", so a
  post that keeps killing the worker does not loop.
- **Not in this change:** Facebook, TikTok and YouTube posting jobs keep the 2026-10-31 rule.
