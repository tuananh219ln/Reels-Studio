# 2026-11-17 — "Phân tích đối thủ" M5: the Videos tab, posting dates read from samples of the grid, comparing competitors

The last round of the spec (`Competitor Analyzer (Facebook)` v0.1, §10 M5), asked by tuananh219ln after M1–M4
([2026-11-17-competitor-analyzer](2026-11-17-competitor-analyzer.md), whose decisions stand).

- **The Videos tab is optional, after Reels.** "Quét cả tab Video" on the page, or `include_videos` on
  `competitor_scan_start`, sets `scope.videos`; the extension (1.4.0) then reads `<page>/videos/` (`&sk=videos` for a
  profile) the same way, after the Reels grid. Its videos are `type = 'video'`, opened at `watch/?v=<id>`, with
  their own grid places. Off by default: it doubles the time a scan takes and the selectors are as untried as the
  rest. A page without Reels still has its Videos tab read.
- **Posting dates from each video's own page, read in the api.** The extension sends the time as written
  (`posted_raw`: "3 ngày", "Hôm qua lúc 08:30", "17 tháng 10", "October 17, 2024"); `competitors.parse_posted` turns
  it into `posted_at` in Vietnam time (a date without a year is the last such day not after the reading). Relative
  times are only as exact as Facebook wrote them, which the stats' limits say.
- **How often they post, from a few dated samples, not every video.** Opening every video for its date would take
  hours. The grids list newest first, so besides the top videos the extension opens each grid's newest and oldest
  video and one every 50 places (at most 30 per grid). The videos between two dated samples were posted between
  their dates: `stats.frequency` gives, per grid, videos a week over the whole span and over each stretch between
  samples, which shows whether the competitor posts more or less than before. `videos_per_week` is the Reels grid's
  (the Videos grid's when there are no reels).
- **Comparing competitors.** `GET /api/competitors/compare?ids=` and the MCP tool `competitor_compare` put 2–10 of
  the member's competitors side by side, each by its latest scan that read anything (`done` or `partial`): counts by
  type, total, median, highest, buckets, the top 10's share, videos a week, the newest posting date. Numbers in
  code; what differs in topics and approach is for the member's Claude. The page has "So sánh" for the ticked rows.
