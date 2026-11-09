# 2026-11-09 — What a member made, only they delete

Part 4 of [docs/specs/per-user-settings-ownership](../specs/per-user-settings-ownership/brief.md), the owner's brief of
2026-11-09: with the tool shared by the team, one member could delete another's work. This narrows, for deleting
only, "There is no self-signup and there are no roles" (2026-10-31) and the entries that left a shared thing to any
member: "“Kết nối Fanpage” is a card per Page; only a Page never posted to can be deleted" (2026-11-03, now also only
by the Page's owner), and the shared libraries of "Every list of the team's work starts on the member's own"
(2026-11-08: Kho tư liệu, Thư viện nhạc and Kho kiến thức stay shared to see and use, but not to delete).

- **The rule** ([ownership.py](../../api/src/reels_api/ownership.py)): only the member who made a thing deletes it;
  anyone else is refused (403), and the web shows no "Xóa" to them. No exception for anyone, as the brief chose.
  Seeing, using and editing are unchanged.
- **What it covers**: a video and its scenes, a topic group, a plan idea, a saved template, an affiliate product, a
  Kho tư liệu item, a music track, an article, a sample video, a note, a render machine, and taking a post down. A
  Page is stopped ("Ngừng dùng", which unlinks it from posting) or removed only by its owner. A member's own
  defaults and connections were already theirs alone.
- **A parent never takes a teammate's work with it**: a video with a teammate's post, note or queue place, a group
  with a teammate's video, idea or product, and a plan whose replaced days hold a teammate's idea are refused (409),
  naming what is in the way.
- **MCP the same**: `delete_scene`, `delete_layer` and `delete_sound` act only on the connected member's own videos.
  On the web, a layer or a sound is still removed by whoever edits the video, as editing stays shared; through MCP
  the brief asks for every deletion to be the member's own.
- **Makers that were never kept**: topic groups and plan ideas get `created_by_id` (migration 0068), filled from who
  last changed them (as Pages got their owners, 2026-11-03), else a group's first video's maker, an idea's group's
  maker. A group still without one (as "Sức khỏe" may be) is deleted by nobody until the owner decides otherwise.
- Text box styles keep no maker and stay deletable by any member, out of the brief's list.
