# 2026-11-11 — A plan file is loaded in one of four modes, and a day's extra ideas are backups

Brief [docs/specs/nap-ke-hoach-tuy-chon](../specs/nap-ke-hoach-tuy-chon/brief.md), decided by the owner (namtc) on
2026-11-11 after a 14-day plan had to be re-imported whole to change days 4, 7 and 9. It adds to "Saving a new plan
replaces every idea" (2026-11-03) and "Saving an imported or AI plan replaces the 30 days only" (2026-11-04) without
reversing them: the AI draft and "Ghi đè toàn bộ" still do exactly that.

- **Four modes for a file** ("Cách nạp" in its preview, `POST /api/plans/{id}/apply`): "Ghi đè toàn bộ" (the
  default, as before), "Thêm vào cuối ngày" (the file's ideas after those of the same day; an empty day is filled),
  "Thêm vào ngày trống tiếp theo" (the file's days in order into the first empty days, from day 1) and "Thay các
  ngày có trong file" (only those days, at the owner's call of 16:10 that day). Days the file does not name are not
  touched in the last three. The file format does not change.
- **A topic is still never twice in a plan** (2026-11-04). The brief asks to skip a file idea whose topic its target
  day already has; a topic on another day is skipped the same way and reported with where it is, and one waiting in
  the Backlog moves onto its day with its video, as saving a plan does. A day stops at 10 ideas; the rest is reported.
- **Too few empty days asks first**: the preview warns "Còn X ngày trống, file có Y ngày" and only "Nạp phần vừa"
  loads what fits; the api refuses the same load (409) unless told to fit.
- **Replacing days follows the overwrite's rules**: refused when those days hold a teammate's idea, and an idea that
  keeps the topic of a replaced one keeps its video. Loading never deletes a video.
- **Every load reports** the days filled, added to, replaced or emptied, the ideas skipped and the file's days that
  found no room, in "Đã nạp kế hoạch".
- **A day's extra ideas are backups for "Bán tự động"**: the semi-automatic round makes the first ideas of a day up to
  the group's ideas per day (`plan_per_day`, "Số ý tưởng mỗi ngày", the AI's "[Số video mỗi ngày]"), in the day's
  order; an idea that already has its video holds its place, so a day is never made twice. This narrows "one run per
  idea and day" (2026-11-08, semi-automatic posting) for days with more ideas than that number; a plan kept at its
  ideas per day is made as before. "Tạo video" and MCP's "Đọc ý tưởng kế hoạch 30 ngày" are unchanged: a member, or
  the morning job's prompt (to be updated once this is live, per the brief), chooses.
