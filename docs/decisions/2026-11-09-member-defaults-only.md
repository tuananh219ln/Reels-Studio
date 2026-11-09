# 2026-11-09 — Video defaults are only each member's own; the team's level is gone

Part 3 of [docs/specs/per-user-settings-ownership](../specs/per-user-settings-ownership/brief.md), the owner's brief of
2026-11-09. Replaces, in [decisions.md](../decisions.md), the entry "2026-11-08 — Each member has their own video
defaults; the team's start those who have none" in its team part (the team's defaults, edited by any member, starting
everyone without their own), and in "2026-11-08 — A topic group may have its own voice…" the last step of the order
("› the team's" becomes "› the app's built-in"). The rest of both stands.

- **A new video starts only from its maker's own defaults**, however it is made (the web, a plan's idea, MCP, a sample
  video); a clone keeps its source's as before. No teammate's settings reach another member's videos.
- **A member who never saved their own** starts from the app's built-in defaults (`video_options.built_in_defaults`),
  not from the team's or anyone else's. "Về mặc định gốc" on the page drops their own and goes back to these
  (the old "Dùng mặc định nhóm", `DELETE /api/settings/my-video-defaults`).
- **The switch keeps behaviour**: migration 0067 gives every member without their own a copy of the team's defaults
  as they were, so nobody's new videos change on the day. The team's row (`app_settings.video_defaults`) is kept for
  a rollback but nothing reads it, and `GET`/`PUT /api/settings/video-defaults` are removed, so it cannot be edited.
- Cài đặt › Thiết lập mặc định shows only the member's own, tagged "Của tôi (theo người dùng)" and saying it is their
  account's own setting, not the team's. The settings themselves are unchanged; only whose they are changed.
