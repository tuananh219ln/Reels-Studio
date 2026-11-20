# 2026-11-20 — A new video starts on no channel unless its group has one of the maker's Pages

Reverses the single-brand fallback of the 2026-11-13 brand decision: `brands.default_for` returned the
member's only brand with a logo for any group.

- **Incident 20/11:** the member's only logo brand ("Ăn Ngon Mỗi Ngày", id 6) was auto-attached to all 6
  Threads Day-9 videos (topic 9) at creation, and its logo was burned into their MP4s — though the logo
  belongs only to that Page's videos. The Page-level "Video của Page tự gắn logo" toggle being off did not
  stop it: the video's logo switch was unset, so the brand's `logo_default_on` (True) decided it.
- **Change:** `brands.default_for` now returns only the brand whose active Page is in the video's topic
  group, else None. A lone brand is never the default for a group its Page is not in. Videos of the brand's
  own Page (Ăn Ngon Mỗi Ngày clones) still start on it, logo on.
- **Already-created videos keep their brand:** clear it in Thiết lập → "Kênh của video" → Clear (the MCP
  `update_video` tool cannot clear a brand or the logo switch — it drops those fields silently, like
  `pinned_comment`).
- **Tests:** `test_a_new_video_starts_on_the_members_only_channel_with_the_logo_on` rewritten as
  `test_a_new_video_gets_no_brand_when_its_group_has_none_of_the_members_pages`; new
  `test_a_new_video_starts_on_the_members_only_channel_when_its_page_is_in_the_group` covers the brand's
  own Page with a single brand.
