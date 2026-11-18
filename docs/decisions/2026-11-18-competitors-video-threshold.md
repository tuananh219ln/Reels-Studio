# 2026-11-18 — A big competitor channel keeps only its videos of 100K views or more

Spec v2 §4.9, asked by tuananh219ln, the part [2026-11-18-competitors-ui-v2](2026-11-18-competitors-ui-v2.md) left out
for the owner to decide. Earlier competitor decisions stand, with two changes: a scan no longer always keeps every
video it reads, and its numbers are no longer always summed from the videos kept.

- **A channel is "big" with 10 or more videos of 100K or more** (`BIG_CHANNEL_MIN_HITS`, `MIN_VIEWS_THRESHOLD` in
  `competitors.py`). Only then, and only for the videos kept, are those under 100K dropped. The spec wanted both
  numbers in Cài đặt; they are constants for now, since nothing else in Cài đặt is per competitor.
- **Done in the api when a scan ends, not in the extension.** The extension still sends every video (the spec had it
  send `{views}` alone for those under the threshold), so members need no new extension and the rule can change
  without one. The cost is the api briefly holding rows it then deletes (at most 2,000 a scan).
- **The numbers are taken first and kept apart.** Before anything is dropped, `competitors.stats` sums everything read
  and `apply_threshold` stores that as `competitor_scans.stats_snapshot`; `stats()` answers with it, so the total,
  median, buckets, top 10's share and posting frequency (which needs the grid's places) are those of all 300 videos,
  and every MCP tool and "So sánh" keep reporting them. The spec's four `bucket_*` columns are inside the snapshot.
  `scanned_count`, `stored_count` and `threshold_applied` say what was read, kept and from how many views.
- **A video whose own page was read stays** (it has a caption or a posting date), as do those with no readable views:
  the captions and the dated timeline samples belong to them. Only a finished (`done`) scan is cut; a stopped one keeps
  everything, and "Tiếp tục" drops the snapshot so the numbers are summed afresh when it ends.
- **Per channel: Tự động, Lấy tất cả, ≥100K, ≥1M** (`competitors.video_threshold_mode`, from the ⋯ menu,
  `PATCH /api/competitors/<id>`). It applies from the next scan that ends; videos already dropped are not read again.
- **Shown** as "23 / 300" with a "≥100K" mark in the Video column and "Video ≥100K view (23)" over the list; a channel
  that kept everything has quick filters Tất cả, ≥10K, ≥100K, ≥1M (`min_views` on the videos endpoint).
- **Existing scans** have no snapshot and keep every video; a threshold applies to the next scan of each channel.
- Still not built: video thumbnails (the extension does not read them) and a link to a failed scan's log (scans are
  not rows of the jobs table, so the reason stays in the scan's tooltip).
