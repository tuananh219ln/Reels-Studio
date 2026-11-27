# 2026-11-27 — PC Shopee's text moves, keeps its number, and the AI cuts the title (#386)

The three things left of the spec "Ẩn chữ & Phụ đề Cộng dồn" (Looper, 2026-11-27) after
[cumulative-captions](2026-11-27-cumulative-captions.md) and [pc-text-tiers](2026-11-27-pc-text-tiers.md). This changes both on the
points they said were "not built yet".

- **The scene's number stays (built).** Under "Cộng dồn" a content scene's own text is replaced, so its "3." would vanish: it
  stays as the orange circle (`tiers.number_circle`) for the scene's first 2.5 s, just above the first phrase
  (`cumulative.number_corner`, 14% or 62% zone). It pops in over 150 ms and fades with its last 150 ms.
- **The AI cuts the title (built).** For the group PC Shopee the script prompt asks for `title_tiers` (`small`, `main`, `sub`,
  `label`, `extra`) in the same call that writes the script (`jobs.TITLE_TIERS_FORMAT`, added in `jobs.script_prompt`, which the
  script job, the clone job and a member's own Claude through MCP all use), so it costs no extra call. With the three-tier
  title the title scene's text is the tiers as lines (`jobs.title_text`), and `extra` (the words that did not fit, "xem trước
  khi mua") goes to the head of the caption. Other groups, and a title in a box, are unchanged; an answer without a `main` line
  leaves the first title as written.
- **Motion by short stills, not by filters** (`reels_render/motion.py`): a picture is replaced by a few stills, each larger
  or fainter than the last, that follow each other with no gap, then the picture itself. No looped input is needed.
  - A phrase's **first word pops in over 180 ms** (115% to 100%, faint to sharp; its first still is already 35% opaque, so no
    frame is empty). A phrase's **last step fades out over its last 150 ms**.
  - **Deviation from the spec:** a later word of a phrase appears at once; it does not pop on its own. A pop for each word
    would triple the pictures of a long video, and the picture holds the whole phrase, so the previous words would pulse too.
- **Cost, measured** on a synthetic video (4 scenes of 10 s, 3 with a 25-word narration, FFmpeg 9.0.2, this machine): render
  16.2–17.6 s without motion, 18.4–18.7 s with it (about 1.12x, the spec's limit is 1.5x). Inputs 97 to 169, FFmpeg's command line
  16.8k to 28.2k characters. **That second figure is the risk:** Windows allows 32,767 characters in a command line, so a
  render machine on Windows with a longer "Cộng dồn" video can fail at launch (the video before this change already took 17k
  for 97 inputs). Linux (the Docker worker) allows 128 KB for the filter graph itself. Moving the graph into a file needs
  `-filter_complex_script` (gone in FFmpeg 8+) or `-/filter_complex` (only FFmpeg 7+; Debian 12 has 5.1): left for a decision
  on which FFmpeg the render machines run.
- **Not built (left in #386):** the title bouncing line by line (80 ms apart, 80% to 105% to 100%) and a scene's text shrinking to
  96% as it fades. Both need a time-dependent scale on a box that is overlaid inside each scene's graph; the title's box has
  no looped input to scale. The studio player and the preview do not animate (they show the settled picture), so they do not
  yet match the MP4 in motion. The page and the preview do not show the number circle yet either.
- **A person watches the render** (the spec's checklist for the motion): an agent cannot judge the feel of a 180 ms pop.
