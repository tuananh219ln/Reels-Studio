/**
 * After a deploy went live, tells the team's Telegram group what it brought ("Có gì mới",
 * docs/decisions/2026-11-26-whats-new.md): the changes in public/changelog.json that this deploy wrote. Needs the repo
 * secrets TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID; without them, without the file, or with nothing new it sends
 * nothing. A failure is only logged: the deploy has already gone live.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { type Changelog, telegramMessage } from "../src/lib/changelog.ts";

const token = process.env.TELEGRAM_BOT_TOKEN;
const chat = process.env.TELEGRAM_CHAT_ID;
const api = (process.env.TELEGRAM_API_URL || "https://api.telegram.org").replace(/\/$/, "");

try {
  if (!token || !chat) {
    console.log("Telegram: no TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID, nothing sent");
  } else {
    const file = path.resolve(import.meta.dirname, "..", "public", "changelog.json");
    const changelog = JSON.parse(readFileSync(file, "utf8")) as Changelog;
    const text = telegramMessage(changelog, process.env.WEB_URL || "");
    if (!text) {
      console.log("Telegram: this deploy brought no change for members, nothing sent");
    } else {
      const response = await fetch(`${api}/bot${token}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chat, text, parse_mode: "HTML", disable_web_page_preview: true }),
      });
      console.log(response.ok ? "Telegram: sent" : `Telegram answered ${response.status}`);
    }
  }
} catch (err) {
  console.warn(`Telegram not sent: ${err instanceof Error ? err.message : String(err)}`);
}
