# 2026-11-17 — "Phân tích đối thủ": a competitor's Facebook Reels read in the member's own Chrome, analysed by their Claude through MCP

From the spec "Competitor Analyzer (Facebook) cho MKT-Tools" v0.1, built in Reels Studio by tuananh219ln's choice in
the session (not in MKT-Tools: Reels Studio already has the members' MCP connection and the Chrome extension). This
round is the spec's M1 to M4; M5 (the Videos tab, posting dates, comparing competitors) is
[2026-11-17-competitor-m5](2026-11-17-competitor-m5.md).

- **Read in the member's browser, never by the server.** Facebook shows a Page's Reels grid and its view counts only to
  a signed-in browser that runs its JavaScript, so the team's extension (`extension/`, 1.2.0) does it, as Google Ảnh
  photos are taken ([2026-11-08](../decisions.md)). The Graph API gives no views of another's Page, and paid scraping
  services were not chosen. It differs from "never by scraping" for Shopee, Google and TikTok (2026-11-02, 2026-11-03,
  2026-11-14), which keep the app's server from reading those sites: here the member's own Chrome reads what it is
  shown. The member accepts the risk the spec names (Facebook's terms; the account used may be restricted).
- **Always as a second Facebook account, signed in by its cookies, in an incognito window** (tuananh219ln's
  choice, 2026-11-17). The member pastes the account's cookies (a `Cookie:` header or a Cookie-Editor JSON export;
  `c_user` and `xs` required) on the extension's options page. They stay in that Chrome
  (`chrome.storage.local`), never reach Reels Studio's server (the spec's "no cookie on the backend"), and are set
  only in the cookie store of the incognito window a scan opens, so the member's own Facebook in normal windows is
  never touched or logged out. The extension needs "Cho phép ở chế độ ẩn danh"; without a saved account or that
  permission the page claims no scan and says what is missing. A scan never falls back to the member's own
  account. The cookies are not shared between members: each Chrome holds its own.
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
- **The top reels' own pages (M3).** After the grid, the page asks the api for the `fetch_captions_top_n` most
  viewed reels (30 by default, 0–100) and the extension opens each `/reel/<id>/` in the same window, 4–8 s apart:
  caption (after "Xem thêm"), the sound's name (`/reels/audio/` link), the video's length, and the reaction,
  comment and share counts read from aria-labels, normalized like views. A field not shown keeps what was read
  before. These selectors are guesses until tried on real pages, and live in `selectors.json`.
- **Sample comments (M4): text and likes only.** For the first `fetch_comments_top_n` of those reels (10 by
  default, at most 30 and never more than `fetch_captions_top_n`) the extension opens the comments and keeps up
  to 30 of the first shown: each comment's text and likes, never who wrote it (`competitor_comments`). A new
  reading replaces a reel's sample; one with no comments keeps it. They are evidence for viewers' pains, read by
  the assistant with `competitor_video_details`, and, like captions, data rather than instructions.
- **Reports are the assistant's, the numbers the app's (M4).** `competitor_report_save` keeps the markdown and the
  topics, pains and recommendations the member's Claude wrote, and adds the scan's `competitor_stats` at that
  moment as `summary`, whatever the markdown says. Every save is kept; the newest is shown under the scan on
  `/competitors` (as plain text, copyable: the web has no markdown renderer) and read by `competitor_report_get`.
- **Numbers in code, analysis on the member's plan.** Views are normalized from the grid's text in the api
  (`competitors.parse_views`: K/N/nghìn, M/Tr/triệu, B/Tỷ, either "." or "," as the decimal mark); `competitor_stats`
  sums, takes the median, buckets and the top 10's share. Topics, pains and recommendations are written by the
  member's Claude from `competitor_top_videos`, which carries the spec's analysis prompt; no AI cost to the team.
- **Differences from the spec.** Integer ids, as every table here. Competitors were each member's own; since
  [2026-11-17-competitor-team-read](2026-11-17-competitor-team-read.md) the whole team reads them and only the
  member who scans one changes it. `kind` is `profile` only for a `profile.php` / `people/` address; a vanity name is `page`. The grid has
  only views; caption, sound and counts are read for the top reels only, and the posting date not at all, so
  posting frequency stays null until M5. The spec's `comment_sample` and `report` tables are
  `competitor_comments` and `competitor_reports`.
