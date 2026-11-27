# 2026-11-28 — Turning Shopee links into affiliate links without the Open API (plan, not built yet)

Asked by the owner (Nam dev). The team cannot get a Shopee Open API App ID (the owner believes it needs a business tax
code; not confirmed on Shopee's pages), so `generateShortLink` is out of reach. The Custom Link CSV flow
([2026-11-24](2026-11-24-custom-link-excel.md)) works but needs a manual upload per batch. The owner chose
"extension first, `an_redir` as a stopgap".

**This partly reverses [2026-11-24](2026-11-24-custom-link-excel.md)**, which said "the app does not call Shopee": the
extension would call Shopee's Custom Link from the member's own logged-in Chrome. The server still never does.

## Plan

1. **Extension** (`extension/`): for the member's products with a product page and no saved link, send the pages in
   batches to the same internal endpoint Shopee's Custom Link page uses
   (`affiliate.shopee.vn/api/v3/gql?q=batchCustomLink`) with the member's own session, `Sub_id1 = p<page>`, and give the
   returned `s.shopee.vn/...` links to the app through the existing import rules (`apply_rows`). Also reads name and
   image from the product page in the member's browser. Needs a sample request from the owner before coding.
2. **Stopgap `an_redir` link**: `https://s.shopee.vn/an_redir?origin_link=<product page>&affiliate_id=<member's
   Affiliate ID>&sub_id1=p<page>`, stored on the account (new column) and shown as "link tạm". Shopee does not document
   this redirect, so it is **not** used by default until three test links show clicks and orders under their sub id in
   Shopee Affiliate's report.
3. **Telegram bot**: several Shopee links in one private message are added to the sender's products (same rules as the
   web's "dán link", at most 50), then follow 1 or 2.

## Not done on purpose

No scraping with a fake `TelegramBot` user agent (it dodges Shopee's anti-bot), and no cashback model.

## Open

- Is the Open API really closed to a personal account? The owner opens `affiliate.shopee.vn/open_api` to check.
- Does `an_redir` keep `sub_id` and count commission? Unverified.
