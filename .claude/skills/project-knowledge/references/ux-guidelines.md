# UX Guidelines

## Interface Language

**UI language:** Vietnamese only. There is no i18n for the UI.

**Content language:** a separate per-video setting. It is `vi` in the MVP, and `en` comes later.
Do not confuse it with the UI language: the script, TTS voice, and knowledge rules follow the
content language.

**Tone:** short, plain Vietnamese for an internal team. Use action-verb buttons such as "Tạo kịch
bản", "Render", "Tải MP4", "Chạy lại".

## Screens (MVP)

- **Login.**
- **Video list:** status of each video and its latest render.
- **Script and scene editor:**
  - choose 1 of 5 titles;
  - edit scene text using `*word*` markup to color a keyword red;
  - assign or upload an image per scene;
  - edit caption, hashtags, and affiliate suggestions;
  - toggle TTS and choose music;
  - see the banned-word warnings and Claude's self-review list.
- **Knowledge Base:**
  - edit each document and trigger "AI soạn nháp" (AI draft);
  - view the food bank table with draft or approved status and source links;
  - approve rows.
- **Music library:** upload licensed tracks.
- **Job log:** status, duration, MP4 download, re-run.

## Video Template

There is one fixed template in the MVP, derived from the reference channel (see
[content.md](content.md#video-formula)).

- **Frame:** 9:16 vertical, 1080×1920 at 30 fps. Photos are cover-cropped from the centre, with
  no black bars.
- **First frame = thumbnail:**
  - a close-up food photo filling the frame, with vivid color;
  - the chosen title in a text box centred in the frame, 3–5 lines, with no fade-in.
- **Text box:**
  - yellow background (`#FFD60A`) with black text (`#111111`). The "yellow text with a black
    outline" style was rejected because it is hard to read on bright photos;
  - bold, uppercase, centered, at most 960 px wide;
  - keywords marked `*...*` are drawn in red (`#E10600`);
  - long text wraps and shrinks, and is rejected only if it still does not fit: the title starts
    at 96 px and shrinks to 64 px (at most 5 lines); body text starts at 84 px and shrinks to
    60 px (at most 3 lines).
- **Body scenes:**
  - one item per scene, 3–5 seconds each (the renderer accepts any length of 1 s or more);
  - the item name plus one benefit line, separated by a manual line break;
  - text box in the lower third, with its bottom edge at y = 1440, clear of the food and of the
    platforms' caption and button area.
- **Motion:** every scene zooms in linearly around the centre, from 1.00 to 1.12. Scenes are
  joined by a 0.4 s crossfade centred on the boundary, so the total length equals the summed
  scene seconds.
- **Audio:** soft instrumental music from the team library at volume 0.25 by default, looped or
  cut to the video length, with a 1.5 s fade-out; plus TTS when enabled.
- **Font:** must render Vietnamese diacritics. The default is Be Vietnam Pro Black.
- **Length:** derived from the scene count. A title scene plus 5–7 scenes runs about 20–40 seconds.
