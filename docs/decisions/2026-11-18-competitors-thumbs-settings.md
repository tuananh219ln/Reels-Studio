# 2026-11-18 — Competitor video pictures, and the big-channel rule set in Cài đặt

Finishes what [2026-11-18-competitors-video-threshold](2026-11-18-competitors-video-threshold.md) and
[2026-11-18-competitors-ui-v2](2026-11-18-competitors-ui-v2.md) left out. Both stand, with the changes below.

- **The rule is a team setting, no longer constants.** Cài đặt › Phân tích đối thủ (`/settings/competitors`, in the
  team's group) sets how many videos of how many views make a channel big: `min_hits` 1 to 100 (10 by default) and
  `min_views` 1.000 to 100.000.000 (100.000 by default), saved as the `competitor_threshold` row of the `settings` table
  (`GET`/`PUT /api/competitors/settings`). It is what "Tự động" uses; a channel's own "≥100K" and "≥1M" modes stay
  fixed. It applies to scans that end afterwards. Unlike the other shared settings it is not in the tab's edit history
  (2026-11-09): it holds two numbers and nothing secret, so `settings_log` is not extended for it yet.
- **A video's picture is a small copy of ours, for the videos whose own page the extension opens.** Those are the
  most viewed ones (30 by default) and the timeline samples, not every video of the grid: opening every one would take
  hours (M5). On each reel's page the extension reads `og:image`, its background fetches and shrinks it to 128 px
  (as the avatar, 2026-11-18 ui-v2), and the api re-encodes it as a JPEG under `competitors/<id>/thumbs/<video id>.jpg`,
  served to members at `GET /api/competitors/<id>/thumbs/<video id>` (`competitor_videos.thumb_key`, migration 0103).
  A video with no picture shows none. A video holding a picture is never dropped by the big-channel rule. Extension
  1.6.0; the page still asks only for 1.5.0, since older ones simply send no pictures.
- **Not built:** the link to a failed scan's log. Scans are not rows of `jobs`, so the reason stays in the scan's
  tooltip; making them jobs would change how scans are claimed and is not worth it for a link.
