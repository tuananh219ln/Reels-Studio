# 2026-11-18: a channel's avatar is the Page's own, and the competitor table sorts from its headers

## Context

After the first real scans, several channels showed the same avatar: the second Facebook account's own picture.
When a Page has no `og:image`, the extension took the first `svg image` of the page, which is the account's picture
in Facebook's top bar. The table also drew the "≥100K" mark as a tag beside the counts and let the scan progress
wrap, and sorting was only in the "Sắp xếp" box.

## Decision

- **Avatar (extension 1.6.1, `pageAvatar` in `extension/facebook-reels.js`):** `og:image` first; else the first square
  picture of at least 40 px in the smallest block around the Page's name, then in the main area. A picture inside
  Facebook's top bar or side columns (`role` banner, navigation, complementary) is never taken. None found means no
  avatar (the coloured initial), never the account's. A channel that kept a wrong avatar gets the right one from
  "Cập nhật thông tin kênh" or a re-scan with 1.6.1.
- **Table:** the Kênh, Video, Tổng view, Trung vị and Quét gần nhất headers sort the list, one direction each (names
  A to Z, numbers biggest first), and stay in step with the "Sắp xếp" box and the address. The Video cell is two lines
  like the channel beside it ("30 / 50", then "≥100K view"), and a running scan's progress is one short line
  ("10/500 video", then "Top video 0/10").

## Verification

E2E: a page drawn like Facebook's (top bar, cover, Page avatar, a reaction icon) gives the Page's picture, and none
once it is removed; a header click sorts and moves the box. Needs a person to try a real scan with 1.6.1.

## Correction (extension 1.6.2)

1.6.1 put the avatar search in a helper beside `reelsStudioReadMeta`; Chrome injects that function alone, so the
helper was missing on Facebook and the whole header (name, followers, avatar) was lost. The search now lives inside
the function, and a failure there still sends the name and followers. The name is also the first `h1` of the main
area outside Facebook's own parts (Messenger's panel, a `dialog`, has an `h1` "Đoạn chat" that became a channel's
name). The E2E test runs the function's source alone in the page, as Chrome does.

## Fixed extension id (1.6.2)

The cookies are in `chrome.storage.local`, which Chrome keys by the extension's id; an unpacked extension without a
`key` gets its id from its folder's path, so loading an update from another folder lost the cookies. `manifest.json`
now carries a fixed public `key` (id `ncnafhaoejkcbljpkomboinfnmkgolph`; no private key is needed for an unpacked
extension, and none is kept). The cookies still never leave the member's Chrome. Removing the extension still deletes
them; `extension/README.md` says to update with the reload arrow instead.

## Profiles' grids and the grid's name (1.6.3)

Every profile (`profile.php?id=…`) stopped at 10 reels: its grid scrolls in a box of its own, and the scan scrolled
only the window. The scan now brings the last reel card into view each round (whichever box scrolls), then scrolls the
window as before. The grid's own name reading leaves Facebook's parts out like the header's, and the header's name
wins over the grid's at the end of a scan, so "Đoạn chat" no longer comes back with a video scan. Checked in headless
Chromium against a page drawn that way: 1.6.2 read 10 of 40 and "Đoạn chat", 1.6.3 all 40 and the Page's name; the
same page is now an E2E test.
