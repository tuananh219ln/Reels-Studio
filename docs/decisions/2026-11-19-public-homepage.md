# 2026-11-19: The homepage is public, for TikTok's app review

## Context

TikTok rejected the app "Reels Studio" (submitted 2026-11-07) on one point, App name: the website must clearly show
the app name and match the registered website, privacy and terms URLs. `/` was only a redirect to the login, so a
stranger saw no description of the product. Direct Post stays blocked until the app passes review.

## Decision

- `/` is a public landing page (the proxy matcher leaves it open, like `/login`, `/privacy` and `/terms`): the name,
  the description registered with TikTok word for word, a short "how it works" that matches the registered scopes
  (`user.info.basic`, `video.upload`, `video.publish`), links to `/privacy` and `/terms`, and a "Đăng nhập" link to
  `/login`. It is in English because reviewers read the portal's English description; the rest of the app stays Vietnamese.
- A visitor with the session cookie still goes to `/videos`. The cookie name moved to `web/src/lib/session.ts`, so a
  page does not import `proxy.ts` (a Node proxy that OpenNext on Cloudflare supports only experimentally).
- Not changed: `/terms` and `/privacy` still describe an internal tool of about five people. If TikTok rejects the
  app again on that, rewriting them is the next step, and it is the owner's call.

## Consequences

The owner resubmits the app in the TikTok portal after this is deployed (Return to Draft, then resubmit); nothing in
the portal changes. Approval is TikTok's decision and is not guaranteed.
