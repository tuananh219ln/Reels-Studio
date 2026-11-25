# 2026-11-25 — "Đồng bộ bài ngoài app" also imports Instagram Reels; "Kiểm tra ngay" also checks the Page's posts

Asked by the owner, with [2026-11-25-recheck-live-posts](2026-11-25-recheck-live-posts.md).

- **Instagram Reels posted outside the app are imported** with the Page's Facebook reels, by the same switch ("Đồng bộ bài
  đăng ngoài app"), the same hourly round and the same "Đồng bộ ngay": `instagram.account_reels` reads the Page's linked
  account's `/media` (`media_product_type = REELS` only, up to 4 pages of 50) since `last_synced_at` less 2 hours (30 days
  back the first time). A Reel the app has (`external_id`) is skipped; a new one is a `meta_suite` post of platform
  `instagram`, matched to a video as a Facebook reel is (Instagram gives no length, so the match has none) and read at once
  by the numbers round. No migration: `one_target` already admits `meta_suite` posts with no video.
- **One platform failing does not stop the other.** `sync_error` keeps the first failure ("Instagram: …" for Instagram) and
  `last_synced_at` moves on only when both read, so the one that failed is read from the same time next round.
- **"Kiểm tra ngay" on a Page also has its live posts checked**: it clears `checked_at` of the Page's `published` Facebook
  and Instagram posts, which makes each due for a check at once (`metrics.recheck_due`); the worker does them a few per
  round, so a request never calls a platform (2026-11-03). Posts already deleted and other Pages' posts are not touched.
- **Not done:** TikTok and YouTube are not imported by themselves (their members paste links or connect an account).
