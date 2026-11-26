# 2026-11-26 — "Chiến lược & Kịch bản theo nhịp": Muse writes them, the left column of a Muse video shows them

Asked by the owner (namtc), spec "Luồng duyệt video Muse" §3.3 and §4.1, second round after
[2026-11-26-review-gate](2026-11-26-review-gate.md). Built here: the data and the left column. Versions, "Muse làm bản
khác", the reminder, email and web push are the next rounds.

- **Two columns on the video** (`videos.strategy`, `videos.beats`, migration 0131), as the spec's JSON: the strategy is
  `{content_type, audience, pain_point, promise}` with the five content types of the spec; a beat is
  `{id, type, start, end, text, scene_ids, alt_hooks?, items?, affiliate_product_id?}` with the spec's fourteen types.
  Validated by [strategy.py](../../api/src/reels_api/strategy.py): known types, 20 beats at most, seconds from 0 to 180,
  scene ids that belong to the video, a hook has up to 5 other hooks.
- **Muse writes them with `set_video_strategy`** after it made the video and put the scenes in, naming the real scene
  ids (the spec's "s0" are the scenes' ids here). Only the part sent is replaced. It does not touch the scenes.
- **A beat describes the script; the video is still its scenes.** On the page, a changed beat text is written to the
  first scene the beat names (through the scene's own save), so the MP4 goes out of date and approving asks for a new
  render (the existing `RENDER_OUTDATED` blocker). A beat that names no scene (the spec's "pain") only keeps its text.
  The first save, and what Muse saves, never rewrite scenes.
- **The left column changes only for a Muse video that has beats** (`assistant_app = "Muse"` and beats): "Chiến lược nội
  dung" and "Kịch bản theo nhịp" replace the scenes block, "Thêm cảnh", the scene-count banner and the title / kind row.
  A Muse video without beats, and every other video, keeps the scene editor: hiding it where there is no beats list
  would leave a member nothing to edit with (this narrows the spec's "bỏ hẳn" for Muse videos).
- **What a row does:** its seconds open the MP4 at that second; "Đổi hook" lists the other hooks and the replaced one
  becomes a choice; "Gắn sản phẩm affiliate" opens the products tab; QC items of its scenes (and "Nhịp chưa có cảnh",
  a `warn` of the review gate) show on it, each item carrying a `beat`.
- **Not in this round:** changing the content type from its chip (it means a new version from Muse), "Áp dụng & render
  lại" on the three lines (they do not reach the render), the strategy and beats as `video_versions` rows, a "Muse
  viết lại caption" button. "Tiêu đề & caption" on the "Đăng bài" tab has the title (the title scene's text) and
  "Copy caption + hashtag"; the caption and hashtags are still edited in "Nội dung đăng" just below.
