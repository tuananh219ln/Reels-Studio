import { expect, test } from "@playwright/test";
import { loginAsSeed, resetDatabase } from "./helpers";

/*
 * "Phân tích đối thủ" (docs/decisions/2026-11-17-competitor-analyzer.md). Playwright does not load the Chrome
 * extension: the page is given a stand-in that answers the messages its app.js and background.js send, with a fixed
 * Reels grid, so the page's side (claim, batches, finish) runs against the real api.
 */

test.beforeEach(() => resetDatabase());

test("a pasted link is scanned through the extension and its top videos are listed", async ({ page }) => {
  await page.addInitScript(() => {
    window.addEventListener("message", (event) => {
      const data = event.data;
      if (event.source !== window || data?.source !== "reels-page") {
        return;
      }
      const answer = (body: object) => window.postMessage({ source: "reels-extension", ...body }, "*");
      if (data.type === "hello") {
        answer({ type: "ready", version: "1.1.0" });
      } else if (data.type === "scan-reels") {
        (window as unknown as { __scanned: string }).__scanned = data.url;
        answer({ type: "answer", id: data.id, started: true });
        const videos = [
          { fb_video_id: "1000001", views_raw: "4,5M", position: 0 },
          { fb_video_id: "1000002", views_raw: "288K", position: 1 },
          { fb_video_id: "1000003", views_raw: "7,6 N", position: 2 },
        ];
        answer({ type: "scan-batch", scanId: data.scanId, videos });
        answer({ type: "scan-done", scanId: data.scanId, status: "done", name: "Linh Đoàn" });
      }
    });
  });
  await loginAsSeed(page);
  await page.goto("/competitors");
  await expect(page.getByText("Tiện ích đã sẵn sàng.", { exact: false })).toBeVisible();

  await page.getByLabel("Link Facebook của đối thủ").fill("https://m.facebook.com/linhdoan/reels/?ref=share");
  await page.getByRole("button", { name: "Quét", exact: true }).click();

  const row = page.getByRole("row", { name: /Linh Đoàn/ });
  await expect(row.getByText("Xong", { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(row.getByText("3 video", { exact: true })).toBeVisible();
  await expect(row.getByText("4.795.600", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { __scanned: string }).__scanned)).toBe(
    "https://www.facebook.com/linhdoan/reels/",
  );

  await row.getByRole("button", { name: /Expand row|Mở rộng/ }).click();
  const top = page.getByRole("row", { name: /https:\/\/www\.facebook\.com\/reel\/1000001\// });
  await expect(top.getByText("4.500.000", { exact: true })).toBeVisible();
});

test("without the extension the page says how to install it", async ({ page }) => {
  await loginAsSeed(page);
  await page.goto("/competitors");
  await expect(page.getByText("Chưa thấy tiện ích Reels Studio")).toBeVisible();
});
