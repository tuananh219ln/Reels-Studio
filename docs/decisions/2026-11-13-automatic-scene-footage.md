# 2026-11-13 — Automatically find and select footage without pasted links

The owner (namtc) asked for real footage and more realistic visuals, including reused public clips, and explicitly
rejected having to find TikTok/YouTube links by hand. This adds an opt-in automated video path to the `photos` job.
It extends the stock-only worker decision of 2026-11-08 for **public YouTube videos**, without changing Google
Images' browser-only path or adding a paid search service.

- **One shared switch, off until enabled**: Cài đặt › Nguồn tư liệu › "Tự tìm và chọn clip theo kịch bản".
  `app_settings.auto_footage` uses the existing settings table, with edit history. Enabling it also enables
  `auto_photos`, the existing post-script job switch. Off by default avoids silently increasing the team's LLM
  spending; enabling it once applies to subsequent script/clone jobs, not only one video.
- **No pasted links**: the worker searches YouTube with the scene's first Vietnamese keyword (English if absent).
  One bounded `yt-dlp` search considers ten results, keeps at most three non-live videos of 2–90 seconds, and
  constructs canonical URLs only from validated video ids. Pexels/Pixabay video search follows in the group's
  source order, respecting disabled sources and missing keys. TikTok and Facebook automatic search are not shipped.
- **Choose by looking**: at most one unused candidate per source, three per scene. The active image-capable LLM
  sees two frames from each of six possible windows, centre-cropped to 9:16 as in the render, and may choose a
  window or reject the video. Malformed or
  out-of-range choices are rejected. Selection is not a guarantee of factual or visual correctness.
- **Bounded work and spending**: YouTube search has a 40-second total timeout; each download has 80 seconds and
  50 MB limits. No cookies, login, user configuration or plugins are used. A provider error stops further selection
  calls for the job; paid attempts are recorded before the request. Source failures fall back instead of failing
  the script. No jobs or paid provider calls are run against production for verification.
  `yt-dlp[default]` bundles its YouTube JS solver at install time; the worker's existing Node 22 runs it. Runtime
  fetching of remote solver components is disabled.
- **Existing rendering**: the chosen stretch becomes a normal silent scene clip, cut with FFmpeg and validated
  by `check_clip`; source URL and the automatic-review mark stay on the scene. Script timing and existing media
  are preserved. In `single` mode only the title may become a clip: content photos are still needed for insets.
  No render-core or video-template changes. No automatic rendering or posting is added.
- **Fallback**: no suitable clip (including source blocking or a model without image support) means the existing
  photo search. That search's old limits and review requirement remain. Missing photos still block render as before.

The fully automated search is limited to the implemented sources; it does not promise downloading every public
YouTube video. YouTube may change or block its public endpoints. Pexels/Pixabay and then photos remain fallbacks.
