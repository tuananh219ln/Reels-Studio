# 2026-11-17 — "Phân tích đối thủ": a competitor's Facebook Reels read in the member's own Chrome, analysed by their Claude through MCP

From the spec "Competitor Analyzer (Facebook) cho MKT-Tools" v0.1, built in Reels Studio by tuananh219ln's choice in
the session (not in MKT-Tools: Reels Studio already has the members' MCP connection and the Chrome extension). This
round is the spec's M1 and M2; M3–M5 are later work.

- **Read in the member's browser, never by the server.** Facebook shows a Page's Reels grid and its view counts only to
  a signed-in browser that runs its JavaScript, so the team's extension (`extension/`, 1.1.0) does it, as Google Ảnh
  photos are taken ([2026-11-08](../decisions.md)). The Graph API gives no views of another's Page, and paid scraping
  services were not chosen. It differs from "never by scraping" for Shopee, Google and TikTok (2026-11-02, 2026-11-03,
  2026-11-14), which keep the app's server from reading those sites: here the member's own Chrome reads what it is
  shown. The member accepts the risk the spec names (Facebook's terms; the account used may be restricted): the page
  advises a second Facebook account.
- **The open "Đối thủ" page drives the extension.** A scan is queued (on the page, or by the member's Claude with
  `competitor_scan_start`); the member's open `/competitors` page claims it (`POST /api/competitors/scanner/claim`),
  has the extension open the grid in a window of their Chrome, and saves the batches it reads. The extension keeps no
  token and calls no api: the page's own session does. Claiming marks the extension online for MCP's answer.
- **Like a person, and it stops at a checkpoint.** One scan at a time per member; a scroll every 1.5–3 s (random), the
  end after four scrolls with nothing new, at `max_videos` (500 by default) or after 30 minutes. A checkpoint, login
  or "temporarily blocked" page stops it as `partial`, left in front for the member; it is never answered. The
  selectors are in `extension/selectors.json` and follow links and text, never Facebook's generated class names.
- **Resumable without duplicates.** A scan whose page was closed (silent for 3 minutes) is claimed again; "Tiếp tục"
  queues a `partial` or `failed` one. Videos are unique per scan (`fb_video_id`), so reading the grid again updates
  them; a reading without a number keeps the number read before.
- **Numbers in code, analysis on the member's plan.** Views are normalized from the grid's text in the api
  (`competitors.parse_views`: K/N/nghìn, M/Tr/triệu, B/Tỷ, either "." or "," as the decimal mark); `competitor_stats`
  sums, takes the median, buckets and the top 10's share. Topics, pains and recommendations are written by the
  member's Claude from `competitor_top_videos`, which carries the spec's analysis prompt; no AI cost to the team.
- **Differences from the spec.** Integer ids, as every table here. Competitors are each member's own (no team
  sharing). `kind` is `profile` only for a `profile.php` / `people/` address; a vanity name is `page`. The grid has
  only views, so caption, date and reactions stay empty until M3; posting frequency is null until dates are read.
  `comment_sample` and `report` tables, `competitor_video_details` and `competitor_report_save/get` come with M3/M4.
