# 2026-11-09 — Edits are logged where they are made, and any member puts a version back

Asked by the owner (namtc) on 2026-11-09: who changed a prompt or a video, and what it was before, could not be
seen, and a mistaken save (or "Khôi phục mặc định") lost the text for good.

- **Logged where it is edited**: every create, edit, delete and restore goes to `edit_logs`
  ([edit_log.py](../../api/src/reels_api/edit_log.py)), with whole values before and after, and is shown on the
  screen where the thing is edited ("Lịch sử" on each card, a "sửa lần cuối" line under the thing's name), not on a
  page of its own. Kho kiến thức (topic groups, their prompts, banned words, photo hint, voice, templates and plan
  settings) is the first; videos, articles, Pages, settings and the libraries follow in later rounds, in that order.
- **Any member puts a version back** ("Khôi phục bản này"), as editing is shared: a restore is a new entry, nothing
  is removed, and the member is asked first when later edits would be replaced. Only what depends on nothing else
  is restored: text and lists (prompts, banned words, photo hint, voice). A name, templates and plan settings are
  only shown; renders, posts, AI rewrites and secrets will never be restored from the log (secrets are logged as
  "đã đổi", never their value).
- **"Khôi phục mặc định" is gone** from the prompts and the plan prompt: the app's default is a version of its own
  in the history ("Bản mặc định của app"), put back the same way, so going back to it can be undone.
- **Deleted things**: the log keeps a deleted group's name and what it held, readable in the list's history. Bringing
  a deleted thing back is not done from the log (its files may be gone); a "Thùng rác" is a later round.
- **Kept with no end date** for now; the rows are small (a prompt is at most 20,000 characters). Edits made before
  this have no history: the first logged save keeps the version it replaced ("Bản trước khi có lịch sử").
- Changes through MCP and the semi-automatic round are tagged by `source` once those edits are logged; topic groups
  are not edited through either today.
