# 2026-11-23 — UI consistency sweep: links, statuses, notes, colours, number formats

Asked by the owner (namtc) on 2026-11-23 after the Quản lý kênh review ("làm hết"): the same problems as on that
screen were looked for on the others and fixed where the rule already existed. No rule was reversed.

- **Navigation is a link.** Cards, rows, tabs and the editor rail open in a new tab on right, middle or Ctrl/Cmd click
  (`stretch-host` / `stretched-link` in globals.css, `rowLink` in lib/rowLink.ts, real `<Link>` in the Cài đặt tabs
  and the rail icons). Already the rule in ux-guidelines "Keyboard and focus"; the code had drifted from it.
- **A status is a dot and a word.** `StatusText` replaced the coloured Tags that showed a status (rework, unsaved
  changes, prompt state, comment tracker, pasted-link result, chosen Shopee product, import counts, the small-photo
  warning). `toneOf` maps a colour an existing table carries to a tone. Left as Tags on purpose: kinds, platforms,
  topics, "Mặc định", and the six pipeline stages of the 30-day plan and the article plan, whose colours must be told
  apart (a dot has only seven tones).
- **A note is grey text, not a banner.** `Hint` replaces info Alerts that only explained something. Alerts stay for
  errors and warnings that block. The 4 remaining info alerts show a state of the page (the picked plan idea, a running
  job) and the install note for iPhone, and were kept.
- **Colours.** `COLORS` gained success, danger and the check-result fills; stray greys and orange outlines use the
  theme. Brand colours of platforms and the video/photo mock-ups stay as they are.
- **Numbers.** `lib/format.ts` holds the vi-VN count, trimmed-decimal and percent formats the screens kept copies of.
  `formatDecimal` in lib/api.ts (fixed decimals) is a different format and stays.
- **"Của tôi / Cả đội".** Quản lý kênh and Tài khoản và kênh use the shared `WhoseFilter` (new `label` and `allLabel`
  props, so Quản lý kênh still reads "Trang của tôi / Tất cả").
- Not changed: the very large files (VideoPreview, PlanTab, SceneCard, videos/page, knowledge/page) are not split in
  this change; a split without a person watching the screens would risk more than it fixes.
