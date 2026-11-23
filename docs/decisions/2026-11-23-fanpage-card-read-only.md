# 2026-11-23 — Quản lý kênh: the Page card is read-only, settings are in a drawer

Asked by the owner (namtc) on 2026-11-23, who found the Page card crowded: five selects and switches, three long
explanations and the logo buttons, so cards differed in height and "chưa liên kết" rows looked like errors. They chose
the read-only card with a drawer among four sketches (read-only, hybrid, table, both).

- The card keeps the Page's name, token status, the four numbers, the posting line and the footer. Where it had
  controls it now has one line per platform (a dot and a few words, via StatusText, joined with commas) and a "Cài đặt"
  button for the owner.
- "Cài đặt" opens the same drawer the Page dashboard already had ("Tài khoản và chủ Page"); the controls themselves
  (`OwnerLine`) are unchanged, so no api, permission or text of a control changed.
- No existing decision is reversed: the status dot, the comma rule and "owner-only accounts"
  ([2026-11-13-fanpage-tiktok-account](2026-11-13-fanpage-tiktok-account.md)) are kept. The TikTok account is still "picked
  once on the Page card" in that decision's words, now through its "Cài đặt".
- Not done, left for later: a table view and search or token filter on the page (about 7 Pages for now).
- Tests: the e2e specs that picked an account on the card (`affiliate`, `videos`, `shared-actions`) open "Cài đặt" first;
  the card's lines are asserted after a reload.
