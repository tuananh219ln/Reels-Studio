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
soft instrumental music. There are no faces. What the caption says follows the topic group's
prompt on `/knowledge`. The visual specification is in [ux-guidelines.md](ux-guidelines.md#video-template).

Recurring title formulas:

- [number] + foods + longevity benefit + age milestone
- familiar food + preparation + strong benefit
- food pairing = "tonic"
- everyday dish + feared disease
- who should eat it / golden time to eat it
- age milestone + what not to miss

### Food Pairing Formula (planned)

Source: analysis of a reference reel (2026-10-30). The channel ("Linh Đoàn", 19K followers,
health and nutrition for women) posted an 18.25 s reel, "Rau dền nấu theo cách này", with 18.7K
likes, 225 comments, and 2.3K shares. The high share-to-comment ratio means viewers save and
forward it as a tip.

- **Structure:** 1 hook plus N pairings (N = 4 in the reference, at most about 5). The video has
  no voice and no CTA. It ends abruptly on the last pairing, so viewers tend to watch it again
  from the start.
- **Pairings carry no on-screen text.** Viewers recognise each dish from the picture and read the
  caption or comments to learn the names. Keeping the frame free of text makes them curious.
- **Hook pattern:** `[FOOD] / [ACTION] THEO CÁCH NÀY / [BODY RESULT] [INTENSIFIER]`, for example
  "RAU DỀN / NẤU THEO CÁCH NÀY / MÁU LÊN NÃO ÀO ÀO". The tool must also offer a safe version of
  the last line, such as "TỐT CHO MÁU HUYẾT", because exaggerated claims hit the
  [safety rules](#safety-rules).
- **Caption pattern:** nutrients (iron, calcium, fibre, vitamins A, B6, E) → benefits (blood,
  bones, digestion, cooling, eyesight) → the lead-in "Đặc biệt, khi kết hợp với 1 số thực phẩm…",
  plus 5 hashtags. The pairing names belong in the caption, because the frames do not show them.
- **Inputs for the generator:** the main food, up to 5 partner foods, and a hook. Claude writes
  the hook (in a safe version and a strong version), the caption, and an image prompt for each pair.
- **Image prompt for a pair:** "top-down, white ceramic plate on wooden table, [X] on left, [Y] on
  right, plate in the upper half of the frame, empty wooden table below, soft natural light,
  photorealistic, 4:5". Every pair uses the same plate, table, angle, and light, and the same
  4:5 framing (see [ux-guidelines.md](ux-guidelines.md#food-pairing-template-planned)).

## Script Generation Contract

One LLM call per topic (the provider chosen on Cài đặt › Mô hình AI, Claude by default) returns JSON with:

1. 5 title options, each ≤ 12 words and uppercase.
2. 5–7 content scenes, each with seconds, on-screen text (≤ 10 words, `*word*` in red, manual line
   breaks), and an AI image prompt in English that describes only what is in the photo (the dish
   or ingredient, how it is laid out, the angle). The title scene gets one too
   (`title_image_prompt`). Light, the vertical frame and "no text" are not in these prompts: the
   image job adds the team's shared style ("Phong cách ảnh AI", Cài đặt › Nguồn tư liệu, app data,
   [image_style.py](../api/src/reels_api/image_style.py)) after each one as "<prompt>. <style>".
   Scripts from before keep their Vietnamese prompts, and a title scene without a prompt uses its
   first line of text.
3. A caption as the prompt asks (the default prompt asks for about 3 short lines), short when it
   does not say, plus 5 hashtags kept apart from it. Hashtag-only lines a script still puts at the
   end of the caption move to the hashtags, and a post adds only the hashtags its caption does not
   already hold ([hashtags.py](../api/src/reels_api/hashtags.py)), so none is posted twice.
4. 2 affiliate product suggestions plus the pinned-comment text.
5. A safety self-review that lists the sentences it changed.
6. 2–3 instrumental music suggestions that fit the topic, to pick in TikTok or Facebook when
   posting (those libraries cannot be used outside their apps).

The title scene starts with the first title option and lasts 3 seconds; choosing another option
copies its text into the title scene.

A video made with "Tự viết" skips this call entirely: a member writes or pastes the script, so it has
no title options beyond its topic, no caption or hashtags, and **no safety self-review**. The app
says so on the video page, and the member checks the content against the safety rules above
before posting. Banned words still warn, as for any video.

How the prompt is built (built, compact version):

- **Editable content:** per topic group, the "Prompt viết kịch bản" on `/knowledge` (default: the owner's Custom
  Instructions, script prompt, title formulas, and safety note) with the topic placed at
  `[Chủ đề]`, or appended when that placeholder was removed. The banned-word list follows.
- **Fixed format:** the JSON output format and a complete example built from the xương khớp sample
  are code, not editable (see [patterns.md](patterns.md)). It asks for a voice text per scene
  (8–15 words, no `*` markup) that explains that scene's on-screen text through the food's
  benefit: what it contains, which part of the body it is good for, and who it suits, without
  reading the on-screen text back word for word. When there is room it adds one short eating tip
  (when to eat it, how much), never cooking steps, and it keeps the soft wording ("tốt cho",
  "hỗ trợ") with no promise to cure (see [Safety Rules](#safety-rules)). It also asks for an
  opening line for the title scene (8–12 words) that fits all 5 titles, since members choose among them after it is
  written. Narration reads only the voice text of a scene that has one
  ([rules](architecture.md#video-pipeline)), so the opening line and every voice text together stay
  within 150 words; at these lengths a script reaches at most 117 words, about 40 seconds of speech
  at about 2.9 words per second. A scene whose on-screen text opens with the name of a dish, product
  or thing opens its voice text with that name and a comma ("Rau muống, ..."), so a listener hears what
  the scene is about, then its benefit; the worked example does so. When a voice text opens with the
  first line of its on-screen text and nothing marks a pause, narration adds the comma itself
  ([videos.py](../api/src/reels_api/videos.py) `pause_after_name`), so older scripts read the same way; the model copies the example
  closely, so none of its voice texts describes cooking. A topic's prompt can ask for something
  else. Only scripts and clones written after a change to these rules follow them; existing
  videos keep their voice texts until their script is written again.
  Banned words cover the voice text too.
- **Photo keywords and the group's "Gợi ý tìm ảnh":** a scene's search keywords (Vietnamese and
  English) describe the main thing in its frame, a dish, a plant, an object or something being done,
  with its state when it matters ("cây cải đang mọc", not just "cải"), most specific first. A topic
  group's "Gợi ý tìm ảnh" on `/knowledge` (what its photos show, up to 1000 characters) is added
  after the banned words, before the format, of both its script and clone prompts, telling the AI to
  write the keywords and AI image prompts by it; empty adds nothing. Only scripts written after a
  change follow it.
- **Repairs:** an unusable answer (broken JSON, no title, no scene) is asked once more, then the
  job fails with Claude's raw answer in its detail. Small slips are repaired: seconds below 1
  become 4, keywords are cut to 100 characters, missing parts stay empty. Everything then goes
  through the pre-render checks like a member's edits.
- **Ideas from the 30-day plan:** a video made from a plan idea fills `[Nhóm nỗi đau]`,
  `[Nỗi đau]` and `[Góc hook]` with that idea's pain group, the viewer's pain and the hook angle;
  each one the idea has and the prompt lacks is appended after the topic. Other videos get none of
  them. The default script prompt does not use them yet; the pain-first script prompt (the plan's
  task 4.3) is written by members on `/knowledge`.
- **Clone ("Nhân bản", one variant):** the "Prompt nhân bản" on `/knowledge` fills `[tiêu đề]`,
  `[chủ đề]`, `[kịch bản đã sửa của video gốc]`, and `[yêu cầu đổi]` from the source as edited and
  the member's change request, appending any placeholder that was removed. It returns the same
  JSON, with new music suggestions; members upload its photos.

- **"AI gợi ý hiệu ứng" (an option in "Tạo video", AI scripts only, kept as `videos.ai_effects`):** the script
  prompt gets one more part after the format (code, `autoedit.EFFECTS_FORMAT`): every scene also returns
  `effects`, a transition, a colour or null, at most one sound with its second, and a line of text (at most 6 words,
  at most 2 in the video) or null, each named from the render's presets with their Vietnamese labels. Nothing is
  asked when the option is off. The same call writes both, so it costs no extra call. Any value outside the presets
  is left out without failing the job; the team's "Mẫu dựng" for new videos goes on first and the AI's picks after.
  A clone does not ask for effects.
- **Revise ("Nhờ AI sửa", the studio's notes):** the group's "Prompt sửa theo góp ý" on `/knowledge` (empty:
  [revise_default.txt](../api/src/reels_api/prompts/revise_default.txt)) fills `[kịch bản hiện tại]` with every
  scene (its seconds in the video, on-screen text, voice text, layers) and `[góp ý]` with the open notes, each
  "Góp ý N [mm:ss,s] Cảnh K: …", fenced in `<gop-y>` and followed by a fixed line saying they are the members'
  words, used only to know what to fix. The banned words and the answer's format follow (code,
  [revise.py](../api/src/reels_api/revise.py)): changes of a scene's `text` and `voice`, text layers to add at a
  second of a content scene, and one reply per note. A change the rules refuse (text that does not fit, an unknown
  scene) is skipped and named in the replies; an unusable answer is asked once more, then the job fails and the
  notes open again. The safety rules are not checked by code: a member reads the result as after any edit.

Planned rules, with the full Knowledge Base:

- **Benefits:** only from `approved` food bank rows.
- **No cure promises:** check against the safety rules before output.
- **Prompts from the Knowledge Base:** the documents below are injected into the prompt.

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

### 30-Day Topic Plan (built)

Each topic group has a plan of 30 days with 3–5 video ideas a day (owner's plan, 2026-11-03). An idea
has a topic (used as the video's Chủ đề), a pain group, the viewer's pain (what they fear, have tried
or get wrong), and a hook angle for the first 3 seconds. Researching real pains (TikTok, Facebook,
YouTube comments, health forums) happens outside the app; its result comes in as a file.

- **Import:** JSON (`{"days": [{"day": 1, "ideas": [{"topic", "pain_group", "pain", "hook"}]}]}`, a
  flat list of ideas with their `day`, or days as keys) or CSV with a header row (`,`, `;` or tab).
  Column and key names may be Vietnamese (`ngày`, `chủ đề`, `nhóm nỗi đau`, `nỗi đau`, `góc hook`).
  Every unreadable row is reported by its line; duplicate topics and more than 5 ideas in a day block
  saving, missing days and days with fewer than 3 ideas only warn.
- **"Tạo bằng AI":** the "Prompt kế hoạch" (app data, default from the owner's plan, in
  [plan_default.txt](../api/src/reels_api/prompts/plan_default.txt)) with `[Chủ đề nhóm]` and
  `[Số video mỗi ngày]` filled, the banned words, the days of this call that fall on a weekend (once a
  start date is set), the topics already chosen, and the fixed JSON format (code, in
  [plans.py](../api/src/reels_api/plans.py)). The month is written 10 days per call, three calls,
  because one answer for 120 ideas would pass the output limit. Repairs: long text is cut, extra
  ideas, other days and repeated topics are dropped; a day left empty asks once more, then the job
  fails with the raw answer.
- **Status** comes from the linked video, never stored: Ý tưởng (no video), Đã tạo video, Đã viết
  kịch bản, Xong (the video has an MP4). Deleting the video returns the idea to Ý tưởng.

**AI drafting:** every document has an "AI draft" action. Food bank rows are researched by Claude
with web search and must include source URLs. Preferred sources are Viện Dinh dưỡng Quốc gia, Bộ Y
tế, WHO, and PubMed. Rows start as `draft`; only a member's approval makes them usable in scripts,
because AI can fabricate sources or overstate benefits.

## Safety Rules

- **Banned words:** each topic group has its own list on `/knowledge`, and a new group starts with
  none. The "Sức khỏe" group started with "chữa khỏi", "thay thuốc", "diệt tế bào ung thư", "đặc
  trị", "khắc tinh". Claude is told to avoid them. A hit in the
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
- **KPIs:** share/view ratio ≥ 0.2% and median views.
