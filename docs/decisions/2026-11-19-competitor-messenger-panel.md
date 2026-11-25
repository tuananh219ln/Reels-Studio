# 2026-11-19: the scan hides Messenger's panel and never reads it

## Context

After the second account's cookies were pasted again, Facebook opened Messenger's panel ("Đoạn chat", "Các đoạn
chat của bạn chưa được sao lưu") in the scan window. The readers took the first match on the page, and the panel
comes first: every reel got the caption "Các đoạn chat của bạn chưa được sao lưu", a chat's "5 phút" as its posting
time (so every date was the scan's own and the per-week figures were empty), and a profile the name "Đoạn chat". The
panel carries no `dialog` role, so 1.6.2's rule missed it. Grids also stopped early (profiles at 10, a Page at 90
that once gave 500).

## Decision

- **Extension 1.7.1:** each injected reader first finds Messenger's panel (the highest block around one of
  `selectors.messengerMarkers` that does not hold the page's own content), presses its close button
  (`selectors.messengerClose`), hides it, and never reads inside it or Facebook's bars. A caption equal to a marker is
  refused. The name is only the main area's heading, else the tab title.
- **Grid:** six rounds without a new reel before it stops (was four); on such a round the last card goes to the top
  edge and back so a loader sees it come in again. A grid that stops before the limit says why in the scan's error
  (rounds, whether Messenger was hidden, page height), shown in the status tooltip, so the next short scan can be
  diagnosed from the app.
- **api:** `NOT_A_NAME` (Đoạn chat, Chats, Tin nhắn, …) is never kept as a channel's name, and one kept before is not
  shown (`read_name`).

## Verification

Headless Chromium, the reel reader alone on a page with the panel first: 1.7.0 read the caption "Các đoạn chat…" and
"5 phút", 1.7.1 the reel's own caption and "3 ngày"; the same page is an E2E test. api test for the name. Whether the
grid now loads past 10 on real Facebook is not known: the note on the next scan will say.

## A hidden scan window (extension 1.7.2)

The member confirmed that the scan window was covered or minimised while profiles stopped at 10 reels: Chrome then
reports the page hidden and Facebook loads no more of the grid. Each grid round now checks `visibilityState`; a hidden
round asks the background (`scan-show`) to bring the scan window back (normal, focused) and is not counted as a round
without new reels. After 40 hidden rounds in a row the scan stops as partial, saying to keep the window visible and
press "Tiếp tục". A reel's page is brought back the same way before it is read. The grid's note counts the hidden
rounds. Headless Chromium on a grid that loads only while visible, hidden at first: 1.7.1 read 10 of 40, 1.7.2 all 40
after one `scan-show`; the same page is an E2E test.
