# 2026-11-13 — TikTok has its own caption, derived from the Facebook one

A video has only one caption, and it carries the Facebook hashtag set: the "Copy caption + hashtag" button of the
"Đăng TikTok" card copied that caption as-is, so `#reels`, `#xuhuong`, `#videoviral` and `#trendingreels` went to
TikTok (found by the owner on video 111, 2026-11-13). The nightly build job never mentioned TikTok, and the tool had
no TikTok caption field for it to write.

- **One function derives the TikTok caption** (`hashtags.tiktok_caption`): the caption text without its trailing
  Facebook hashtags (inline at the end of the last line, or on their own lines), then the topic group's TikTok set.
  The video's own hashtag field is never used: it holds the Facebook set.
- **The TikTok set lives in code for now** (`hashtags.TIKTOK_HASHTAGS`, keyed by the group's name): Ăn Lành
  `#suckhoe #songkhoe #anlanh #meosuckhoe` (the owner's decision, 2026-11-12: at most five tags, at most one topic
  tag, replacing the Facebook set, never merged). A group without a set gets the bare caption text. The Facebook sets
  live in the script files and the nightly job body, not in code, so there was no group hashtag setting to sit next
  to; if a second group starts on TikTok, the set becomes a group setting.
- **No new column.** The caption is derived when read, not stored: `GET /api/videos/{id}` (and MCP `get_video`, which
  reads the same payload) returns a computed `tiktok_caption` alongside the unchanged `post_text`.
- **Both TikTok paths use it**: the card's copy button copies `tiktok_caption` (and shows it as a preview), and a
  direct post through TikTok's API sends it as the `title` (`tiktok.post_title` now takes the group's name, not the
  video's hashtags). A draft still carries no caption: the member finishes it in TikTok's app. Facebook posting is
  untouched.

Rejected: a separate stored TikTok caption field (a second caption to keep in sync with the first, for a set that
changes rarely); letting the nightly job write it (there was nothing to write it into); deriving it in the web alone
(the API title needs the same text, so one backend function serves both). The separator between the caption text and
the TikTok set is the same blank line `post_text` uses for Facebook.