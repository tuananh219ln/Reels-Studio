# 2026-11-28 — A render or Facebook check cut off by a worker restart is queued again once

Asked by Nam dev, 2026-11-28: the Telegram bot kept telling members "Render không thành công" and "Kiểm tra bài
Facebook không thành công — Lý do: Worker khởi động lại giữa chừng". Each notice came a few minutes after a PR was merged
to `main`: the deploy stops the worker, the job it was running is cut off, and the new worker marks it failed.

- **Narrows** "a dead worker's job is never re-run automatically" (2026-10-31) further, after
  [2026-11-19 Instagram post after restart](2026-11-19-instagram-post-after-restart.md): `render` and `check` join
  `ig_publish` in `worker.RERUN_AFTER_RESTART`. The cut job still fails with the same reason; the restarted worker adds
  a new queued job (`retry_of_id` the old one, `params.after_restart`), so telegram.py says nothing about it.
- **Why it is safe:** neither spends AI money. A render reuses the narration already made (`make_voices` skips a scene
  whose voice is stored); a check only reads the post from Facebook. A check cut off when a reel's time came would
  otherwise leave the reel shown as scheduled until someone pressed "Kiểm tra".
- **Once only:** cut off a second time, the job stays failed and the member is told, as before.
- **Not in this change:** jobs that call an LLM, TTS-only jobs, and Facebook, TikTok and YouTube posting keep the
  2026-10-31 rule.
