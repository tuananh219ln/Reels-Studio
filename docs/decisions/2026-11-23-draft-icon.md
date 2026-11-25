# 2026-11-23 — A TikTok draft is not drawn as a public post

Asked by the owner (namtc) on 2026-11-23: the platform icon on a video card should say what the post really is. A
TikTok draft the worker sends to the owner's inbox ends as `status = "published"` (the worker's word for "TikTok has it"),
so its icon looked like a public post.

- `GET /api/videos` and `GET /api/videos/{id}` add `posted_states`: `{"tiktok": "draft"}` while every TikTok post of the
  video has `publish_mode = "draft"`; empty otherwise (a direct post, or one recorded by hand with no mode). `posted_on`
  is unchanged, so statuses, filters and counts do not move.
- The icon keeps the platform's real glyph (the same Ant Design icons), with a dashed outline and an amber dot for a
  draft, and a tooltip in words; nothing relies on colour alone. The first sketch dimmed the icon and used letters; both
  were dropped for being hard to see on a dark theme.
- Chosen by the owner among three scopes: only this fix. Not done: a "tự đăng" mark (it needs a new `publications.auto`
  column), a "lần tự đăng cuối" block on the Page card, and a dimmed icon for a private YouTube upload (that upload is not
  in `posted_on`, and putting it there would change what counts as posted).
