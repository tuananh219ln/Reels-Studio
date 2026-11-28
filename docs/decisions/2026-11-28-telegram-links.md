# 2026-11-28 — Shopee links sent to the Telegram bot become the sender's products

Asked by the owner ("làm bot tele nhận link"), after the outside deal bot he studied took a Shopee link in Telegram.
Part of [2026-11-28-shopee-auto-link](2026-11-28-shopee-auto-link.md).

- **Private chat only.** A message in the group is not read for links (the bot's privacy mode already hides it); the
  products are the sender's own, found by their linked Telegram account like the other personal commands.
- **Same rows as the web's paste**: `routes_affiliate._from_links`, at most 50 links per message, a link already listed is
  skipped, a product page is kept as `page_url` and a short link as the member's own `url`. No Shopee call; the worker
  reads details when some account has an App ID, else the product stays a draft the member fills in.
- **Which group**: the first line of the message names it (accents and case ignored); with one group the member may add
  to, that one; otherwise the bot lists the groups and adds nothing. Nothing is remembered between messages, so no state.
- **Not done**: converting the links (the Chrome extension, see the decision above), reading a product's name or photo
  from Shopee's page (that needs a fake browser; refused), a button to pick the group.
