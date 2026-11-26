# 2026-11-26 — Telegram commands: the same in the group and in private, a member's own work always private, no AI

## Context

After private messages ([2026-11-26](2026-11-26-telegram-private.md)) the owner wanted the shared group and the private
chats to offer the same features, personal notices still going privately, and to reach the app's MCP tools and ask
how new features work from Telegram. A bot that understands free text needs an AI called with the team's key (Muse
cannot be used: MCP only goes from Muse to the app). The owner chose the free first step.

## Decision

- **Commands, no AI.** `/cho_duyet`, `/hom_nay`, `/loi`, `/tong_quan`, `/moi`, `/huongdan <words>`, `/help`, the same
  in the group and in a private chat. They read the database, the changelog and the in-app guides; nothing costs money.
- **A member's own work is always answered privately.** Asked in the group, the bot says only "📩 Đã gửi riêng cho …"
  there. The member is known by their linked Telegram account; someone not linked is told how to link. Team-wide
  answers (`/tong_quan` with numbers only, `/moi`, `/huongdan`) are given where they were asked.
- **After Duyệt, one press to the Page's queue** (the member's Pages posting the video's group, through the web's
  "Thêm vào hàng chờ"); **after Bỏ, the bot asks why** and keeps the typed answer on the rejection.
- **A daily summary in the group** at 21:00 Vietnam time (`TELEGRAM_CHAT_ID` on the api and worker): numbers and the
  best video of the last 48 hours, nobody's own work.
- The bot keeps Telegram's privacy mode: in a group it only receives commands addressed to it (`/cmd@bot`, which the
  "/" menu writes).

## Not done

Free-text chat with an AI using every MCP tool (paid per message, with a daily limit per member) is the second step,
left for later by the owner.
