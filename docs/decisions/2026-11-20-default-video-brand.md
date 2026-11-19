# 2026-11-20 — A new video starts on its maker's channel

Asked by tuananh219ln: picking the channel and turning on the logo on every video is a chore when a member makes videos
for one Page ("Ăn Ngon Sống Khỏe").

- **A new video (web, MCP, plan idea, reference video) gets a `brand_id` when it is made**, in
  `video_options.apply_defaults` through `brands.default_for`: among the maker's own brands with a logo, the one whose
  active Page is in the video's topic group, else the only one. With several and none of the group, nothing is picked,
  as before, so a member running several Pages never gets the wrong logo silently.
- **The switch is left unset**, so the brand's "Video của Page tự gắn logo" (`logo_default_on`, on by default) decides
  it; turning that off on the Page's card keeps new videos logo-free.
- **Not a member default:** `brand_id` stays outside `video_options.DEFAULTS` and Cài đặt › Thiết lập mặc định, as
  [2026-11-13-brand-logo](2026-11-13-brand-logo.md) set; it is derived from the Pages the member owns. A teammate's
  channel is never picked, and copies ("Nhân bản", "Tạo bản cho kênh khác") keep their source's as before.
