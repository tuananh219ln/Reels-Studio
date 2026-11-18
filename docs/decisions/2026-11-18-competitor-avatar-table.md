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
