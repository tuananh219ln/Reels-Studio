# 2026-11-14 — The "Đăng bài" status card and the note after posting, as the publish panel spec

Asked by tuananh219ln from a spec ("Đặc tả UI — Publish Panel (Đăng video đa nền tảng)", with a reference picture).
Four points of it were put to the owner first, who chose each time the option noted below.

- **Web only.** The spec's api (`POST /api/videos/:id/publish` with a list of platforms, a `PublishJob` polled every
  2 s, a retry per platform, a TikTok or Facebook sign-in opened by itself when the session ran out) is not built:
  the card keeps the api of [the video editor spec](2026-11-14-video-editor-spec.md), one job per video, the page
  sending the platforms one after the other and "Thử lại" sending the failed job again. The spec's states are read
  from what the video already says (`platformResults`).
- **It reverses the 2×2 grid** of the video editor spec: the platforms are rows of 38 px, the whole row a `<label>`
  toggling a checkbox, in a `<fieldset>`. YouTube Shorts and Instagram stay as before, posted by hand: their rows say
  "Đăng tay", have no checkbox and open "Tùy chọn khác" on their tab. The last pick of Facebook/TikTok is kept per
  member in the browser (`localStorage`, in try/catch): a convenience, not shared state.
- **It reverses where the note after posting sits:** fixed 16 px from the window's top right, 380 px wide (no longer
  measured against the side tabs' line), 8 s instead of 7 when all went out, with "Xem chi tiết →" (to the status card;
  the note stays) and ✕ "Đóng"; `role="alert"` when something failed.
- **Colours are the theme's**, not the spec's `#F05A24` and Inter: orange as text or a thin mark is `COLORS.primary`
  (#C2410C, about 5:1 on white, which the spec's own accessibility part asks for), the button the theme's fill. The
  spec's green, red and their pale backgrounds are used for the result rows and the header's dot.
- **The card's states:** "Sẵn sàng đăng" (never tried), "Đang đăng…" (a platform on its way), "Đã đăng", "Đã đăng một
  phần", "Đăng thất bại", and "Đã hẹn giờ" (only a scheduled Facebook post; the spec has no state for it), each but the
  first with "· dd/mm, hh:mm". `data-state` on the card says the same (`posted` is gone).
- **The MP4 small plays in a window** ("Xem MP4", browser controls, the listening volume under it) instead of in
  place. Its picture is the MP4's first frame: the spec's yellow caption laid over it is not drawn, since the render's
  title frame already shows the title as the viewer will see it.
- **"Render lại" on the card asks first**; while the render runs, the platforms give way to a line saying posting
  waits for the new MP4.
- **"Bình luận ghim:"** says "✓ đã đăng, nhớ ghim trên Facebook", not the spec's "đã ghim": Facebook does not let an
  app pin a comment, so the member still pins it by hand.
- Not built from the spec: a platform row turned off with "Kết nối" when no account is connected (the row stays, and
  the account line under the rows says to connect one, as before), the "TRƯỚC KHI ĐĂNG" label, and "Mở app ↗" on a
  TikTok draft.

No api, data or render change.
