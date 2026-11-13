# 2026-11-13 — Brands ("Kênh"): one logo per brand, laid on the MP4 at render

Asked by tuananh219ln from a spec ("Đặc tả: Logo theo Kênh cho Reels Studio", by Looper). A brand groups one Facebook
Page, one TikTok account and one YouTube channel and has exactly one logo, burned into the MP4 inside a safe zone shared
by Facebook Reels, Instagram Reels, TikTok and YouTube Shorts, so one file serves all of them.

- **Table `brands`** (migration 0082) as in the spec; each existing Page gets a brand of its own (same name, same owner;
  a Page with no owner and no `updated_by` gets none). A Page belongs to at most one brand (`fanpage_id` unique).
- **A video keeps `brand_id` and `logo_enabled` in `videos.options`**, outside `video_options.DEFAULTS`, so they are no
  member's default look and `look_signature` ignores them. `PATCH /videos/{id}` checks them apart
  (`brands.apply_video_options`): a brand of the member's own, 400 `brand_has_no_logo`, 409 `video_already_posted`.
  `logo_enabled` unset means the brand's `logo_default_on`.
- **The logo is part of the MP4 fingerprint while it is on** (`["logo", brand_id, logo_version]`), so a changed brand,
  switch or logo marks the MP4 outdated through the existing `mp4_outdated` and blocks posting, and MP4s rendered
  before stay current. This replaces the spec's separate `rendered_logo` column: the fingerprint already says what the
  MP4 shows, so no second record has to be kept in step with it.
- **The badge is made once at upload** (`reels_render.logo.make_badge`, Pillow: round logo, white ring 5%, soft shadow)
  and laid over the *joined* scenes by one more overlay in the same `filter_complex`, so it stays still through slide
  transitions and zooms. Title scene: 170 px, centred, its centre on the text box's top edge (box top at least 290), or
  with no box its ring 200 px from the top and the text starting at 400. Other scenes: 120 px, ring 60 px from the right
  and 200 px from the top (x 888–1020, y 200–332), the text starting at 370 or lower.
- **A machine on older code refuses** a video with a logo: `RenderOptions.logo` is sent only when on, like `backdrop`.
- **Posting:** a video with the logo on goes only to its brand's Facebook Page (409 `brand_mismatch`, in the publish
  endpoint, the Page queue and the publish job's retry); without the logo it goes anywhere, as before.
- **Reading is team-wide, writing is the owner's**, unlike the spec's "a member sees only their own brands": members
  share videos, so a member opening a teammate's video must see its brand and logo. Linking a Page needs owning it.
- **No "frozen once posted" rule for a logo change** (spec 7.3): a posted video whose brand's logo changes is shown
  outdated like any other edited video; posting it again to another place needs a render.

- **No separate "Quản lý kênh" page** (owner's choice, same day): the logo is managed on the Page's card in Quản lý
  Page (upload, "Dùng ảnh Fanpage", remove, "Video của Page tự gắn logo"); the brand is made on the first logo
  (`POST /api/brands`), and `/api/fanpages` rows carry `brand`. The brands API stays as the card's backend.

Not in this change: the "Tạo bản cho kênh khác" variant copy, the video's Logo card on the Thiết lập tab, the
safe-zone overlay in "Xem trước" and TikTok/YouTube posting checks; they follow in their own PRs.

A person watches a sample MP4 (a title with and without a box, a slide transition, a zoom, logo on and off) against the
spec's safe zone before this is called done.
