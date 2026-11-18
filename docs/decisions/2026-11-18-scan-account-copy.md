# 2026-11-18: the "Đối thủ" page keeps a copy of the second account's cookies, in the member's Chrome

## Context

The second Facebook account's cookies live in the extension's `chrome.storage.local`
([2026-11-17-competitor-analyzer](2026-11-17-competitor-analyzer.md)). Members update the extension by removing it and
loading the new folder ("Load unpacked"); removing an extension deletes its storage, so every update asked for the
cookies again, even with the fixed id of 1.6.2.

## Decision

tuananh219ln's choice (2026-11-18): the Reels Studio page keeps a copy, so an update never asks again.

- The copy is in the page's `localStorage` (`reels-studio-scan-account`) in the same Chrome. It is still never sent
  to Reels Studio's server, which keeps the earlier decision's rule; the page's own scripts can read it.
- Extension 1.7.0 (`syncScanAccount` in `extension/scan-account.js`): each `scan-account` question carries the page's
  copy. With no account saved, a copy that passes `parseScanCookies` (c_user and xs) is saved again. When the
  extension's account is newer than the copy (or there is none), it is handed to the page.
- "Xóa" on the options page leaves `scanAccountRemovedAt`; a copy saved before it is never restored, and the page is
  told to drop it.
- Removing the extension also turns "Cho phép ở chế độ ẩn danh" off; that switch is Chrome's and still has to be set
  again by hand (the page already says so).

## Verification

E2E: scan-account.js against an in-memory storage (taken back on a fresh install, newer cookies handed to the page,
not restored after Xóa, a copy without c_user and xs refused), and the page storing the copy and sending it back.
