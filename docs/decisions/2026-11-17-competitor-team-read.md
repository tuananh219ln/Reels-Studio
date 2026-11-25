# 2026-11-17 — "Phân tích đối thủ" is read by the whole team; only the member who scans a competitor changes it

tuananh219ln's choice (asked whether a teammate can see their analysis), replacing the "Differences from the spec"
point of [2026-11-17-competitor-analyzer](2026-11-17-competitor-analyzer.md) that competitors were each member's own.

- **Everyone reads everything.** Every member sees the team's competitors on `/competitors` (their own first), each
  scan's numbers, top videos, comment samples and reports, and "So sánh" any of them; so does each member's Claude
  through MCP (`competitor_list`, `_scan_get`, `_stats`, `_top_videos`, `_video_details`, `_compare`, `_report_get`).
  As the shared "Kho tư liệu" and "Kho kiến thức".
- **Only the member who scans it changes it.** Scanning a competitor again, "Tiếp tục", sending a scan's data (the
  extension's batches, details, finish) and "Xóa dữ liệu" stay with its owner; a teammate gets 403 `not_scan_owner`,
  and the page shows them "Chỉ <tên> quét lại hoặc xóa được" instead of the buttons. A member's open page claims only
  their own scans, so a scan always runs as the scanner's own second Facebook account.
- **Any member may save a report** on any scan (`competitor_report_save`): it is reading and writing up, not scanning.
  The report keeps whose Claude saved it (`created_by_id`, migration 0100), shown on its card.
- **A teammate who pastes the same link gets their own competitor**, as before (`competitors` stays unique per
  member and address): the list names who scans each one ("Bạn quét", "<tên> quét").
- **The page's first column is "Kênh"**, the competitor's Page name as the scan read it (its address before that);
  "Đối thủ" keeps the link to its Reels and who scans it.
