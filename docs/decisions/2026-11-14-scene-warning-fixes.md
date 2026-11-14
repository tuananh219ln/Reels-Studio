# 2026-11-14 — A scene's reasons carry their field; "Lặp clip" loops a short clip

The spec's "cảnh báo một dòng kèm nút xử lý (ví dụ 'Lặp clip')", left out of
[the scene cards change](2026-11-14-scene-cards-one-open.md) because the api sent reasons as plain text, and asked for
afterwards by tuananh219ln.

- **The api adds `issues`** to each scene: `{message, field, level}` for every reason, beside the `blocking` and
  `warnings` strings it already sends (kept, so the MCP tools, the studio and an older page read them as before). The
  field is what `script_rules.Issue` already carried.
- **The page offers a fix only when one step does it:** "Lặp clip", "Tải ảnh lên", or the cursor put in the field
  to change ("Nhập từ khóa", "Sửa chữ", "Sửa lời đọc", "Sửa số giây"). A banned word or a photo's credit has no
  button: the member decides what to write.
- **"Lặp clip" is a new scene setting** (`scenes.video_loop`, migration 0085), not a page-only trick: the render loops
  the clip from its start time (the backdrop's way, `trim_loops` then `-stream_loop -1`), the browser preview loops it
  too, and the short-clip warning goes while it is on. It joins the MP4 fingerprint only while on, so MP4s rendered
  before stay current. A new, removed or replaced clip clears it; a split copies it.
- **Loop and "Tiếng gốc" exclude each other** (422 either way): a looped clip's own words would drift from their
  captions. Turning one off is the member's call, so the api names the other rather than turning it off itself.
- **Render machines:** the `clip_loop` option is sent only when some scene loops, so a machine on older code refuses
  the video (an option it does not know) instead of holding the last frame.
- The MCP tools do not set the loop yet; the assistant sees it in the scene's `video.loop`.

This changes the render core: a person watches a sample MP4 with a looped short clip (with and without a start time,
at 1× and 2×) before it is called done.
