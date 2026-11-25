# 2026-11-19 — More transitions, photo motions and a stronger zoom

Owner's spec ("Mở rộng hiệu ứng Hình ảnh"): five more transitions, four more photo motions and a "Cực mạnh" zoom on
the "Hình ảnh" settings (Cài đặt › Thiết lập mặc định and the video's "Thiết lập" tab), so videos look more like
real footage. Built as asked, with these choices where the spec met earlier decisions:

- **The video's transitions are the scene transitions' keys.** Phóng qua, Nháy sáng, Chớp đen and Nhoè lia are the
  existing scene transitions `zoom`, `flash`, `black` and `blur` (same `xfade`), not new names (`zoom_through`,
  `flash_white`, ...), since the render looks the video's transition up among the scene ones. Lướt mượt
  (`smooth_slide`, `smoothleft`) is new and is offered per scene too. Stored values stay as they were: Lia ngang is
  still `pan`.
- **Every transition still takes 0.4 s.** The spec's own lengths (0.25–0.5 s, shortened on short scenes) are not
  used: "a cut among transitions is a one-frame fade at the crossfade's offset" (phase 2 of the studio, 2026-11-05)
  keeps one timeline whatever the transitions, so the length and every narration stay where they are.
- **No existing video renders differently** ("changing a default never makes an old video render differently",
  2026-11-01). Nhẹ, Vừa and Mạnh keep 1.06 / 1.12 / 1.18 (not the spec's 1.10 / 1.20 / 1.35), and Zoom vào, Zoom ra
  and Lia ngang stay linear; only the new motions ease in and out (sine). Cực mạnh is the spec's 1.6.
- **Photos are still scaled to 2×, not 4×, before `zoompan`.** 2× already puts its integer steps below one output
  pixel (also at 1.6); 4× would make every render about four times as heavy. zoompan also keeps x and y inside the
  photo, so no motion can show an edge.
- **A saved default the app no longer accepts falls back alone.** Before, one bad value made a member's whole
  defaults the built-in ones; now only that value is.

A person watches a sample MP4 with each new transition and motion, at every zoom, before this is relied on.
