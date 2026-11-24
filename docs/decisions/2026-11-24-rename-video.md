# 2026-11-24 — Rename a video; copies carry one "(bản N)" / "(xáo N)" suffix, not a pile

Asked by tuananh219ln after #384 showed "… (copy) (copy) (copy) (copy)" and #321 "… (copy) (copy) (xáo 2) (xáo 3)".
This changes [2026-11-14-duplicate-video.md](2026-11-14-duplicate-video.md) on one point: the name of "Nhân bản y hệt"
is "… (bản N)" now, not "… (copy)".

- **Rename:** `videos.name` is editable from the video list (pencil on hover, "Đổi tên" first in the "⋮" menu), the
  video page's header ("Tên video", beside but apart from the title scene's text), `PATCH /api/videos/{id}` and the MCP
  `update_video` (`name`; `""` clears). Metadata only: no MP4 is outdated by it, a posted video can be renamed.
- **One suffix:** `videos.base_name` cuts every trailing "(copy)", "(bản N)", "(xáo N)"; "Nhân bản y hệt" adds
  "(bản N)" (N one past the highest on the same base name), "Nhân bản xáo cảnh" adds "(xáo N)" (N from the shuffle's
  root, as before). The web's "Bỏ (copy)" button uses the same rule.
- **Search** of the video list also looks in `name`.
- **Old names:** `python -m reels_api clean-video-names` prints each change (dry run); `--apply` writes. Run by the
  owner, by hand, not a migration, so the list can be checked first. Names may end up equal; accepted.
- **No ownership check on rename**, like every other field of `PATCH /api/videos/{id}` (any member), so the web shows
  the pencil to everyone.
