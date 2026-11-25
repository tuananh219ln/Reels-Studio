# 2026-11-20: the app is installable (PWA) on a phone and a computer, without offline support

## Context

The team wanted to use Reels Studio from a phone as well as a computer. The screens already work at 375 px
([ux-guidelines](../ux-guidelines.md), UI Rules), so what was missing was a home-screen icon and a full-screen
window, plus a how-to.

## Decision

- **Installable only.** `web/src/app/manifest.ts` (standalone, starts at `/videos`, brand colours), icons in
  `web/public/` (192, 512, maskable 512, and 180 for iOS), and the Apple tags in `layout.tsx`. The icons are
  rendered from `web/src/app/icon.svg`; if the logo changes, render them again.
- **No service worker, nothing cached for offline.** The app is a live tool behind a login whose data and videos
  live on the server; a cached page would show stale lists and could outlive a logout. Chrome and Edge no longer
  need a service worker to offer installing. If offline or push is wanted later, that is a new decision.
- **The how-to is "Cài app lên điện thoại" in the account menu**, with steps for iPhone (Safari only), Android and
  computer, and a one-tap "Cài ngay" where the browser offers it. It is hidden once the app runs installed.
- Web and phone stay one app, one account, one set of data; installing changes nothing for anyone who does not.
