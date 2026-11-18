# 2026-11-18 — "Phân tích đối thủ" v2: the channel's name and avatar, a lighter table, a paged video list

From the spec "Tối ưu giao diện Phân tích đối thủ (v2)" (Looper, 2026-11-18), built on the decisions of
[2026-11-17](2026-11-17-competitor-analyzer.md), [M5](2026-11-17-competitor-m5.md) and
[team read](2026-11-17-competitor-team-read.md), all of which stand. Spec §4.9 (keeping only videos of 100K views
or more on big channels) is **not built here**, see the last point.

- **The channel's name is read from the Page's header, before its grid.** Extension 1.5.0 reads the heading (else the
  tab title), the followers as written, whether a verified badge sits by the name, and the avatar's address, and
  sends them with the end of the scan; `finish` keeps them even when the scan stops early. `competitors.name` is the
  spec's `display_name` (no second column), `followers` and `fb_id` already existed; new are `avatar_key`,
  `is_verified`, `custom_name` and `meta_updated_at` (migration 0101). The `handle` is worked out from the address,
  not stored. The shown name is `custom_name`, else the name read, else the handle, else "Kênh …" and the last six
  digits of the id, on the page, in "So sánh" and in MCP (`display_name`).
- **The avatar is a copy of ours, never Facebook's link.** The extension's background fetches it (it may read
  `*.fbcdn.net`, a page may not) and shrinks it to 128 px; the api decodes whatever arrives with Pillow, stores a
  re-encoded JPEG under `competitors/<id>/` and serves it at `GET /api/competitors/<id>/avatar` to signed-in members.
  The server never fetches Facebook's image server itself (the 2026-11-17 rule that the server never opens Facebook).
  Not an image, or too big: ignored, and the avatar already kept stays. Deleting a competitor deletes its file.
- **"Cập nhật thông tin kênh" is a scan that reads only the header** (`competitor_scans.meta_only`, no videos), queued
  by `POST /api/competitors/<id>/refresh-meta` and run by the same claim flow, so one scan at a time per member still
  holds. It is never a competitor's "latest scan" for numbers, "So sánh" or the videos list. The page now needs
  extension **1.5.0**: an older one would read the whole grid for such a scan.
- **Only the member who scans a competitor renames it** (`PATCH /api/competitors/<id>`, `custom_name`; empty restores
  the name read), as for every other change ([team read](2026-11-17-competitor-team-read.md)).
- **The list does the arithmetic.** `GET /api/competitors` gives each row its latest scan's `median_views`,
  `video_count`, `reels_count` and `videos_count` (the spec's `last_scan` is the existing `latest_scan` with these
  added, so MCP and older callers keep working). `GET /api/competitors/<id>/videos` pages the latest scan's videos
  (20 at a time, by views or by posting date, caption search) and says whether the engagement and date columns hold
  anything, so the page hides them when empty; `videos.csv` exports all of them, with a leading apostrophe on any
  caption that starts with `=`, `+`, `-` or `@` so a spreadsheet never runs it.
- **Where the project's UI rules win over the spec.** The sort and status filter and the search are kept in the
  address (`?sort=&status=&q=`, UI Rules) instead of `localStorage`; "·" is not used to join details; the empty and
  error states use `EmptyState`. A row opens on click anywhere that is not a button, link or box, and has a real
  chevron button too. "Quét" is disabled while the extension is offline. A link already in the list is not refused:
  the page says it was already there and queues a fresh scan. Below 768 px the table becomes cards; the floating bar
  lets "So sánh" take 2–5 channels (the api still takes up to 10).
- **Not built yet.** Video thumbnails (the extension does not read them), the job-log link of a failed scan, and
  §4.9. §4.9 changes what is stored: the numbers (total, median, buckets, posting frequency from dated samples) are
  summed from the videos kept, so keeping only 100K+ videos needs the buckets, counts and timeline samples saved
  with the scan before the rest is dropped. That is a change to the numbers every MCP tool reports, so it is its own
  round, to be decided with the owner.
