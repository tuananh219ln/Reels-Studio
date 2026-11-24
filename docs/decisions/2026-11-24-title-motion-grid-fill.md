# 2026-11-24 — The motion title's slots fill the room down to y 1680

The grid was fixed-size tiles (440 × 189) that left about 240 px unused above the Reels caption zone. The slots now
span 60 px side margins and the height from 40 px under the hook box to `SAFE_BOTTOM` (1680), 30 px gaps, no tile taller
than wide (a grid that stops there is centred in the room). 2 dishes sit one over the other, 3 are a wide one over two,
5 end with a centred tile (no more circle). Badge, name and "?" scale with the tile height (badge capped at the approved
sample's 84 px; the name shrinks to stay on one line), the atlas is cut at 2× so the bigger tiles stay sharp, and the
ring and strip use the same area. The hook-box floor of 640 and the cap of 1000 of the earlier decision stay. A person
still has to watch a rendered sample against the approved video 381.

## Follow-up: the ring with many dishes

The first version kept the ring's old bubble size (190 px) and the grid's `white-space:nowrap` leaked into the shared
`.name` rule, so round names were cut off. The ring now takes the whole room: the main dish is 70 % of the reach and a
bubble is the biggest that touches neither the main dish nor its neighbours (about 280 px for 7 around, 295 for 4). A
name inside a round slot wraps to two lines and shrinks to fit the narrow bottom of the circle; a satellite's name drops
the "TRỨNG +" the main dish already says. `nowrap` stays inline on grid names only.
