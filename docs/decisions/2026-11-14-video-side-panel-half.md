# 2026-11-14 — The video page's side panel is half the width again

[The header decision](2026-11-14-video-page-header.md) made the side panel a fixed 440 px column from 1100 px wide.
A member of the team (namtc) asked for the half-and-half split back ("giao diện 50/50"): the scenes and the panel
each take half of the width beside each other, so the panel's tabs, the MP4 card and the caption are not squeezed.

- **From 1100 px wide the scenes and the panel are two equal columns**, the panel never narrower than 440 px (the width
  of the drawer it becomes below 1100 px), still stuck under the fixed header and scrolling on its own.
- The rest of that decision stands: the fixed header, the QC chip, the menu rail and the drawer below 1100 px.
- Not the old 11/24 and 13/24 split: it is exactly half and half, whatever the screen.

No api, data or render change.
