# 2026-11-26 — "Thống kê" gets a card on which video length works best

Asked by the owner (brief: [specs/stats-duration-card/brief.md](../specs/stats-duration-card/brief.md)): to choose between
keeping short videos (45–60s) and going back to longer ones, the page shows the evidence per Page.

- **A card, not a column.** A cell holds only an answer ("45–60s"); the card holds the median and the number of posts of every
  bucket, so the owner sees who wins and by how much. It is under the comparison table, on Facebook only; the table and its
  CSV are unchanged. Instagram has no 48-hour reading.
- **Three buckets: `<45s`, `45–60s`, `>60s`** (not five): with five, most cells stay under the sample minimum in a 7-day
  period. An edge goes to the longer bucket (45.0 s is "45–60s").
- **Length is the MP4's own (`Video.mp4_seconds`)**, measured by the render, not the sum of the scenes' fitted seconds
  (it would load every scene and its voice for each post, and fall back to the nominal seconds after a text edit).
  A video with no MP4 length is left out.
- **Median of the posts read at 48 hours in the chosen period**, per Page, never added across Pages; a deleted or cancelled
  post counts for nothing, like in `analytics.py`. A bucket under `MIN_SAMPLES` (5) posts shows "Chưa đủ mẫu"; "Tốt nhất"
  marks the highest median (all of a tie) only when two buckets have one. The card says its period is the chosen one, unlike
  the table's 60-day "Trung vị 48h".
- The card only shows numbers; changing the format of videos stays the owner's decision.
