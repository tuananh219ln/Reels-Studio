# Content Domain

This file covers what the videos say and the rules behind the prompts. It applies to the first
channel: a Vietnamese faceless "health leaflet" channel about longevity and nutrition.

Source: the owner's plan "Plan Project Knowledge – Kênh Reels Dưỡng sinh & Dinh dưỡng"
(2026-10-27), based on an analysis of a reference channel.

## Audience and Positioning

- **Viewers:** people aged 40–65, plus their adult children who share videos with their parents.
- **Tone:** warm and caring, like a health leaflet.
- **What wins:** longevity, brain/blood circulation, heart, and cancer-related topics for 50+.
  Weight-loss and beauty topics for young women perform poorly.
- **Why it spreads:** numbered lists are easy to save, age milestones (40/45/50) make viewers say
  "that's me", and the foods are familiar and cheap. Shares far exceed comments.
- **Series:** a winning food is reused as a series of 4–5 videos.

## Video Formula

Each reel is a numbered list. A close-up food image carries large black text in a yellow box, with
soft instrumental music. There are no faces. The caption repeats the title and the full list so
viewers save it. The visual specification is in [ux-guidelines.md](ux-guidelines.md#video-template).

Recurring title formulas:

- [number] + foods + longevity benefit + age milestone
- familiar food + preparation + strong benefit
- food pairing = "tonic"
- everyday dish + feared disease
- who should eat it / golden time to eat it
- age milestone + what not to miss

## Script Generation Contract

One Claude call per topic returns JSON with:

1. 5 title options, each ≤ 12 words and uppercase.
2. Search keywords for the title scene's photo.
3. 5–7 content scenes, each with seconds, on-screen text (≤ 10 words, `*word*` in red, manual line
   breaks), photo search keywords (Vietnamese, most specific first, such as the dish name), and a
   9:16 image prompt (realistic photo, natural light, wooden table). Photo search uses the
   keywords, never the image prompt.
4. A caption of 80–120 words plus 5 hashtags.
5. 2 affiliate product suggestions plus the pinned-comment text.
6. A safety self-review that lists the sentences it changed.
7. 2–3 instrumental music suggestions that fit the topic, to pick in TikTok or Facebook when
   posting (those libraries cannot be used outside their apps).

The title scene starts with the first title option and lasts 3 seconds; choosing another option
copies its text into the title scene.

How the prompt is built (built, compact version):

- **Editable content:** the "Prompt viết kịch bản" on `/knowledge` (default: the owner's Custom
  Instructions, script prompt, title formulas, and safety note) with the topic placed at
  `[Chủ đề]`, or appended when that placeholder was removed. The banned-word list follows.
- **Fixed format:** the JSON output format and a complete example built from the xương khớp sample
  are code, not editable (see [patterns.md](patterns.md)).
- **Repairs:** an unusable answer (broken JSON, no title, no scene) is asked once more, then the
  job fails with Claude's raw answer in its detail. Small slips are repaired: seconds below 1
  become 4, keywords are cut to 100 characters, missing parts stay empty. Everything then goes
  through the pre-render checks like a member's edits.
- **Clone ("Nhân bản", one variant):** the "Prompt nhân bản" on `/knowledge` fills `[tiêu đề]`,
  `[chủ đề]`, `[kịch bản đã sửa của video gốc]`, and `[yêu cầu đổi]` from the source as edited and
  the member's change request, appending any placeholder that was removed. It returns the same
  JSON, with new photos and new music suggestions.

Planned rules, with the full Knowledge Base:

- **Benefits:** only from `approved` food bank rows.
- **No cure promises:** check against the safety rules before output.
- **Prompts from the Knowledge Base:** the documents below are injected into the prompt.
- **Winner variants:** analyze why the video won, then propose 10 variants that change the food,
  age milestone, or disease group, ranked by viral potential.

## Knowledge Base

The Knowledge Base will live in the app, be editable by every member, and be injected into
prompts, replacing the owner's Claude Project. Not built yet: today `/knowledge` holds only the two
prompts and the banned words.

| Item | Contents |
|---|---|
| Channel positioning | channel name, audience portrait, value promise, voice, forms of address |
| Title library | sample viral titles and the title formulas |
| Food bank (table) | sourced benefits per food; fields in [architecture.md](architecture.md#data-model) |
| Video format | the template parameters as written guidance for the prompt |
| Script templates | numbered list, food pairing, and "eat it right" frames, plus approved sample scripts |
| Safety rules | banned words, wording guidance |
| Monetization | affiliate products by topic, pinned-comment templates |

A topic calendar (themes, seasonal topics such as flu season, humid season, Tết) arrives together
with scheduling.

**AI drafting:** every document has an "AI draft" action. Food bank rows are researched by Claude
with web search and must include source URLs. Preferred sources are Viện Dinh dưỡng Quốc gia, Bộ Y
tế, WHO, and PubMed. Rows start as `draft`; only a member's approval makes them usable in scripts,
because AI can fabricate sources or overstate benefits.

## Safety Rules

- **Banned words:** the default list is "chữa khỏi", "thay thuốc", "diệt tế bào ung thư", "đặc
  trị", "khắc tinh"; members edit it on `/knowledge`. Claude is told to avoid them. A hit in the
  title scene text, a scene's text, the caption, or the pinned comment shows a yellow warning that
  does not block the render; matching ignores case, Unicode form, and `*` markup. The 5 title
  options are only for choosing and are not checked.
- **Softer wording:** prefer "hỗ trợ" and "tốt cho" over sensational claims such as "khắc tinh tế
  bào K" or "máu lên não ào ào". Meta flags or demonetizes medical wording even when the fact is
  true.
- **Original content:** prefer the team's own food photos, because reused images or video can lose
  monetization. Stock images are a fallback.
- **Deferred:**
  - the disclaimer "Tham khảo, không thay thế tư vấn bác sĩ";
  - the functional-food (TPCN) advertising sentence "không phải là thuốc" for affiliate products.

## Monetization and Publishing Context

The channel makes money in four ways:

- Facebook Reels content monetization.
- Shopee/TikTok Shop affiliate links in a pinned comment.
- Own products sold through the inbox.
- Coaching.

Publishing practice:

- **Posting windows:** 11–12h or 19–21h.
- **Hashtags:** 3–5 per post.
- **Metrics:** recorded 48 hours after posting.
- **Winner rule:** a video above 10× the median views gets 3 variants.
- **KPIs:** share/view ratio ≥ 0.2%, median views, and the count of videos above 10× the median.
