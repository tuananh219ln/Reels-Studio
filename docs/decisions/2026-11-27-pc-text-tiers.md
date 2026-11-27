# 2026-11-27 — PC Shopee's compact text: the title in three tiers, a scene's text in two, "Trên / Dưới" (round 3 of the spec)

Part of the spec "Ẩn chữ & Phụ đề Cộng dồn" (Looper, 2026-11-27); looks are in [2026-11-27-pc-text-styles.md](2026-11-27-pc-text-styles.md).

- **Two options, `title_layout` (`box` | `three_tier`) and `scene_text_layout` (`box` | `two_tier`)**; a new PC Shopee video starts
  with both compact. Every other group keeps the boxes: the options are `box` for them and the MP4 fingerprint leaves them out.
- **The tiers come from the text already there, no new fields.** The title's lines are read as small / main / sub (one line is
  the main one, two are main and sub, three or more small, main and sub), and a line written `[[-50%]]` is the orange label.
  The page shows them as four boxes (Dòng nhỏ, Dòng chính, Dòng phụ, Nhãn) that write the title's text back. A small line needs
  a sub line too (two lines are read as main and sub). A scene's text: the `*marked*` words are the main line, the rest the sub
  line, a leading "3." the orange numbered circle. The spec's "AI suggests the three lines" is **not built**: the full title
  and the caption are untouched, and a member (or their assistant through MCP) writes the tiers.
- **Limits warn, never block:** a title line over 14 characters, a scene's main line over 16 or sub line over 4 words give a
  yellow warning (`videos.tier_warnings`); the line is shrunk to fit 88% of the width (title) or 92% (scene) and renders.
- **The last scene (the call to action) and every other group keep the text box.** The title block is at most about 22% of the
  frame and centred 22% down; a scene's block sits at 62–78%, or in the 14–30% zone when the scene is set to "Trên"
  (`scenes.text_zone`, migration 0141; also used by the "Cộng dồn" captions). A text dragged to a place keeps it.
- **No entrance animation yet** (the title's bounce, the numbered circle's pop): a picture that animates needs a looped input
  per picture on a render that already lays many; the text shows at once. "Ẩn chữ sau X giây" still applies to the scenes'
  tiers, since they are laid as the scene's text picture.
- **The studio's previews and thumbnail** still draw the old box; only the MP4 follows the tiers. A person watches the MP4.
