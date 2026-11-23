# 2026-11-23 — Tài khoản và kênh: one place and one row for every connection

Asked by the owner (namtc) on 2026-11-23: the same accounts were handled in three places in three looks (the block
under the Page cards on Quản lý kênh, Cài đặt › Tài khoản affiliate, and the Page card's own selects). The owner chose
one place, the same UI, and a "Của tôi / Cả nhóm" switch so the team's channels stay visible.

- Adding, connecting again and removing a Shopee account, a TikTok account or a YouTube channel is done only on
  Cài đặt › Tài khoản và kênh (route `/settings/affiliate-accounts` kept, so links and bookmarks work). A Page only
  picks among them, in its "Cài đặt" drawer.
- One `ConnectionRow` for all three platforms. "Của tôi" shows the member's own with their actions and the Pages
  using each; "Cả nhóm" is a read-only list of the TikTok and YouTube channels from `GET /api/channels`.
- The block "Kênh TikTok, YouTube và đồng bộ Facebook" under the Page cards is gone. The per-Page Facebook sync switch
  ("Đồng bộ bài đăng ngoài app") and "Đồng bộ ngay" moved into the Page's "Cài đặt" drawer (`PageSync`), still the
  owner's alone.
- Google's consent now returns to `/settings/affiliate-accounts?youtube=connected|error` (was `/fanpages`).
- Reverses nothing: Shopee stays private to its member ([2026-11-13-fanpage-tiktok-account](2026-11-13-fanpage-tiktok-account.md)
  and the owner-only rule); no api shape changed.
- Tests: the e2e specs that pressed "Kết nối TikTok", "Thêm tài khoản" and "Thêm kênh" now open "Thêm kết nối" first;
  the channel added from its link is asserted on `connection-tiktok`; the Cài đặt tab list reads "Tài khoản và kênh".
