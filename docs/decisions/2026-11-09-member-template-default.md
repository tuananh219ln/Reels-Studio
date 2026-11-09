# 2026-11-09 — "Mẫu cho video mới" is each member's own, and a template never adds a line to the call to action

Part 1 of [docs/specs/per-user-settings-ownership](../specs/per-user-settings-ownership/brief.md), the owner's brief of
2026-11-09. Replaces, in the 2026-11-05 entry "“Xem trước” grows into a studio with tracks…" of [decisions.md](../decisions.md) (the paragraph
"Automatic effects…"), the words "the team … may pick one for every new video": one switch for the whole team let any
member put "Gợi ý của app" on everyone's videos, against the Pages' locked editing standard.

- **Per member**: `users.edit_template_default` (migration 0065), "app", a template id or null. Cấu hình › Mẫu dựng
  shows and saves the signed-in member's own choice under "Của tôi (theo người dùng)"; `GET /api/edit-templates`
  answers `default` for that member. A column on `users` rather than a table: one value per member, and removing a
  template clears it wherever it was chosen.
- **The maker's**: a new video takes the template of the member who made it (`videos.created_by_id`), whatever made
  it (the web, a plan's idea, MCP, a clone, the semi-automatic round). A video with no known maker takes none.
- **No migration of the old choice**: the team's setting was null on production (checked 2026-11-09 00:45), so every
  member starts at "Không áp mẫu nào" and the app setting `edit_template_default` is deleted by the migration;
  nothing reads it any more.
- **The call to action stays as written**: a script always ends on its own call to action, so a template's end layers
  are skipped when the last content scene has text or narration; its transitions, colour, sounds and title music
  still apply. This holds for every apply (a new video's, "Tự dựng" in the studio, MCP). A last scene left empty
  still takes the template's line.
