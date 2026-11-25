import { expect, test } from "@playwright/test";
import { loginAsSeed, resetDatabase } from "./helpers";

test.beforeEach(() => resetDatabase());

test("each AI service card shows how much of its allowance is used", async ({ page }) => {
  await loginAsSeed(page);
  await page.goto("/settings/ai");

  // ElevenLabs answers exactly: the fake plan has used 12,345 of 100,000 characters.
  const elevenlabs = page.getByTestId("usage-elevenlabs");
  await expect(elevenlabs).toContainText("Còn 87.655 ký tự", { timeout: 15_000 });
  await expect(elevenlabs).toContainText("gói creator");
  await expect(elevenlabs).toContainText("Gói làm mới ký tự lúc");

  // Cloudflare: today's neurons from its analytics (1,234.5 of 10,000 in the fake), and when they come back.
  const cloudflare = page.getByTestId("usage-cloudflare");
  await expect(cloudflare).toContainText("/ 10.000 neurons");
  await expect(cloudflare).toContainText("lượt mở lại lúc");

  // Gemini: only the app's own count, with the way to AI Studio.
  const gemini = page.getByTestId("usage-gemini");
  await expect(gemini).toContainText("Hôm nay app đã gọi: 0 ảnh, 0 lần sửa ảnh, 0 lượt đọc lời");
  await expect(gemini.getByRole("link", { name: "Xem hạn mức trên AI Studio" })).toHaveAttribute(
    "href",
    "https://aistudio.google.com/usage",
  );

  await elevenlabs.getByRole("button", { name: "Làm mới" }).click();
  await expect(elevenlabs).toContainText("Còn 87.655 ký tự");
});
