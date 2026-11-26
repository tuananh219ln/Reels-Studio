import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";
import { loginAsSeed, resetDatabase } from "./helpers";

// Private Telegram messages (docs/decisions/2026-11-26-telegram-private.md): a member links their own chat with the
// team's bot. Telegram is the fake one (api/scripts/fake_services.py); the test plays Telegram's webhook call that
// the bot's /start makes.
const TOKEN = "123456:fake-telegram-token";
const WEBHOOK = "http://127.0.0.1:8100/api/telegram/webhook";
const secret = createHash("sha256").update(`reels-telegram-webhook:${TOKEN}`).digest("hex");

test.beforeEach(() => resetDatabase());

test("a member links Telegram from Cài đặt, picks what they hear about and unlinks", async ({ page, request }) => {
  await loginAsSeed(page);
  await page.context().route("https://t.me/**", (route) => route.fulfill({ body: "Telegram" }));
  await page.goto("/settings/telegram");
  await expect(page.getByRole("heading", { name: "Thông báo Telegram" })).toBeVisible();

  const opened = page.context().waitForEvent("page");
  await page.getByRole("button", { name: "Kết nối Telegram" }).click();
  const telegram = await opened;
  const start = new URL(telegram.url());
  expect(start.pathname).toBe("/reels_test_bot");
  await telegram.close();
  await expect(page.getByText("Đang chờ bạn bấm Start trong Telegram")).toBeVisible();

  // The member pressed Start: Telegram tells the api through the webhook, and the page sees it by itself.
  const update = await request.post(WEBHOOK, {
    headers: { "X-Telegram-Bot-Api-Secret-Token": secret },
    data: {
      message: {
        chat: { id: 9001, type: "private" },
        from: { id: 9001, username: "an_reels" },
        text: `/start ${start.searchParams.get("start")}`,
      },
    },
  });
  expect(update.ok()).toBe(true);
  await expect(page.getByText("Đã kết nối với Telegram @an_reels")).toBeVisible();

  await page.getByRole("button", { name: "Gửi tin thử" }).click();
  await expect(page.getByText("Đã gửi tin thử")).toBeVisible();

  const reminder = page.getByRole("switch", { name: "Nhắc việc lúc 8 giờ sáng" });
  await expect(reminder).toBeChecked();
  await reminder.click();
  await expect(reminder).not.toBeChecked();
  await page.reload();
  await expect(page.getByRole("switch", { name: "Nhắc việc lúc 8 giờ sáng" })).not.toBeChecked();

  await page.getByRole("button", { name: "Ngắt kết nối" }).click();
  await expect(page.getByRole("button", { name: "Kết nối Telegram" })).toBeVisible();
});
