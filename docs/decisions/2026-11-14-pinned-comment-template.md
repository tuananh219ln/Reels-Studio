# 2026-11-14 — The pinned comment is a template filled from the scenes

Asked by tuananh219ln from a spec ("Đặc tả: Bình luận ghim tự đồng bộ với tiêu đề & cảnh"): the pinned comment was
written once with the script, so editing, adding, deleting or reordering scenes left it describing another video.

- **Built: the spec's "simplest way".** `videos.pinned_comment` holds a template; `{title}`, `{hook}`, `{count}`,
  `{items}`, `{item_names}`, `{products}` are filled from the title scene and the content scenes whenever the
  comment is shown, copied ("Copy ghim"), checked or written under a reel ([pinned.py](../../api/src/reels_api/pinned.py),
  its twin [pinned.ts](../../web/src/lib/pinned.ts) for the live preview). The rendered text is never stored, so it
  cannot go stale. No migration: a comment written before has no variable and reads as itself; the field then says
  it no longer follows the scenes.
- **A new script** (a script job, "Từ video mẫu", an assistant over MCP) gets `{title}\n{items}\n<the AI's
  question>`; the script output format now asks the AI for that one question only (≤ 100 characters), not the list.
- **Not built** (the spec's hash flow): `mode` auto/manual, `source_hash`/`source_snapshot`, the regenerate /
  acknowledge endpoints, the AI-written intro and its debounced regeneration, the "Khớp/Lệch kịch bản" labels and
  the Render/Đăng 409 dialog. With the list filled by code nothing goes stale, so they are only needed if the opening
  sentence must be rewritten by the AI after a change of subject; the spec allows this part alone.
- **Warnings, never blocking**, from the spec's checks: a title counting other than the scenes ("7 món" over 6, shown
  at the top of the editor); "link" in the pinned comment or a "Bình luận thêm" with no product attached; over 1,500
  characters; and, only for a comment typed without `{items}`/`{item_names}`, a numbered line matching no scene, a
  scene missing, or the scenes out of order.
- **The field and its preview are stacked, not two tabs** as the spec drew: the template ("Bình luận ghim", with
  buttons that insert a variable at the cursor) and "Xem trước" under it, so both are seen at once and the panel's
  own tabs stay the only tabs in it.
- "Video xuyên suốt" (the spec's open question) uses the same list for now: its scenes are still listed one per line.
