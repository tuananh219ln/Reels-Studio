import { readFileSync } from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { expect, test, type Page } from "@playwright/test";
import { loginAsSeed, resetDatabase } from "./helpers";

/*
 * "Phân tích đối thủ" (docs/decisions/2026-11-17-competitor-analyzer.md). Playwright does not load the Chrome
 * extension: the page is given a stand-in that answers the messages its app.js and background.js send (the second
 * account's status, a fixed Reels grid, then each top reel's page), so the page's side runs against the real api.
 */

test.beforeEach(() => resetDatabase());

type Parsed = { cookies: { name: string; value: string }[]; userId: string };

function parseCookies(text: string): Parsed {
  const context: { parseScanCookies?: (text: string) => Parsed } = {};
  // The extension's own file, run as plain code: its functions land on this context.
  vm.runInNewContext(readFileSync(path.resolve(__dirname, "../../extension/scan-account.js"), "utf-8"), context);
  return context.parseScanCookies!(text);
}

test("the second account's cookies are read from a header or a cookie-export JSON, never without c_user and xs", () => {
  expect(parseCookies("cookie: c_user=100099999999999; xs=12%3Aabc; datr=xyz")).toEqual({
    userId: "100099999999999",
    cookies: [
      { name: "c_user", value: "100099999999999" },
      { name: "xs", value: "12%3Aabc" },
      { name: "datr", value: "xyz" },
    ],
  });
  const exported = JSON.stringify([
    { domain: ".facebook.com", name: "c_user", value: "100099999999999" },
    { domain: ".facebook.com", name: "xs", value: "12:abc" },
    { domain: ".google.com", name: "SID", value: "not-facebook" },
  ]);
  expect(parseCookies(exported).cookies.map((cookie) => cookie.name)).toEqual(["c_user", "xs"]);
  expect(() => parseCookies("datr=xyz; fr=1")).toThrow(/c_user hoặc xs/);
  expect(() => parseCookies("[not json")).toThrow(/JSON/);
});

async function standIn(page: Page, account: { userId: string | null; incognito: boolean }) {
  await page.addInitScript((saved) => {
    const seen: { url?: string; details?: string[]; comments?: string[] } = {};
    (window as unknown as { __extension: typeof seen }).__extension = seen;
    window.addEventListener("message", (event) => {
      const data = event.data;
      if (event.source !== window || data?.source !== "reels-page") {
        return;
      }
      const answer = (body: object) => window.postMessage({ source: "reels-extension", ...body }, "*");
      if (data.type === "hello") {
        answer({ type: "ready", version: "1.5.0" });
      } else if (data.type === "scan-account") {
        answer({ type: "answer", id: data.id, ...saved });
      } else if (data.type === "scan-reels") {
        seen.url = data.url;
        answer({ type: "answer", id: data.id, started: true });
        if (data.metaOnly) {
          // "Cập nhật thông tin kênh": the header only, no grid.
          answer({ type: "scan-done", scanId: data.scanId, status: "done", name: "Linh Đoàn HR", followers: "130 N" });
          return;
        }
        const videos = [
          { fb_video_id: "1000001", views_raw: "4,5M", position: 0 },
          { fb_video_id: "1000002", views_raw: "288K", position: 1 },
          { fb_video_id: "1000003", views_raw: "7,6 N", position: 2 },
        ];
        answer({ type: "scan-batch", scanId: data.scanId, videos });
        answer({ type: "scan-grid-done", scanId: data.scanId, name: "Linh Đoàn" });
      } else if (data.type === "scan-details") {
        seen.details = data.ids;
        seen.comments = data.commentIds;
        for (const id of data.ids) {
          answer({
            type: "scan-detail",
            scanId: data.scanId,
            video: {
              fb_video_id: id,
              caption: `Caption của ${id}: 3 món giúp xương chắc`,
              audio_name: "Âm thanh gốc",
              reactions_raw: "1,2K",
              comments_raw: "45",
              shares_raw: null,
              comment_samples: data.commentIds.includes(id)
                ? [{ text: "Mẹ tôi đau gối, ăn được không ạ?", likes_raw: "12" }]
                : [],
            },
          });
        }
        answer({
          type: "scan-done",
          scanId: data.scanId,
          status: "done",
          followers: "125 N",
          is_verified: true,
        });
      }
    });
  }, account);
}

test("a pasted link is scanned with the second account and its top videos get their captions", async ({ page }) => {
  await standIn(page, { userId: "100099999999999", incognito: true });
  await loginAsSeed(page);
  await page.goto("/competitors");
  await expect(page.getByText("quét bằng tài khoản phụ 100099999999999", { exact: false })).toBeVisible();

  await page.getByLabel("Link Facebook của đối thủ").fill("https://m.facebook.com/linhdoan/reels/?ref=share");
  await page.getByRole("button", { name: /^(search )?Quét$/ }).click();

  const row = page.getByRole("row", { name: /Linh Đoàn/ });
  await expect(row.getByText("Xong", { exact: true })).toBeVisible({ timeout: 30_000 });
  // The columns show short numbers, the tooltip the full one; the header read gave followers and the badge.
  await expect(row.getByText("3", { exact: true })).toBeVisible();
  await expect(row.getByText("4,8 Tr", { exact: true })).toBeVisible();
  await expect(row.getByText("125 N theo dõi")).toBeVisible();
  await expect(row.getByLabel("Đã xác minh")).toBeVisible();
  await expect(page.getByTestId("competitor-kpis")).toContainText("4,8 Tr");
  const seen = await page.evaluate(
    () => (window as unknown as { __extension: { url: string; details: string[]; comments: string[] } }).__extension,
  );
  expect(seen.url).toBe("https://www.facebook.com/linhdoan/reels/");
  // The most viewed first, every one of them (30 by default).
  expect(seen.details).toEqual(["1000001", "1000002", "1000003"]);
  // The first 10 of them also have their comments sampled.
  expect(seen.comments).toEqual(["1000001", "1000002", "1000003"]);

  await row.getByRole("button", { name: "Mở rộng Linh Đoàn" }).click();
  await expect(page.getByTestId("competitor-metrics")).toContainText("Số video");
  const top = page.getByTestId("competitor-videos").getByRole("row", { name: /…000001/ });
  await expect(top.getByText("4,5 Tr", { exact: true })).toBeVisible();
  await expect(top.getByText("Caption của 1000001: 3 món giúp xương chắc")).toBeVisible();
  await expect(top.getByText("1,2 N cảm xúc, 45 bình luận, — chia sẻ", { exact: true })).toBeVisible();
  // Nothing is left to load: 3/3, and no "Xem thêm".
  await expect(page.getByTestId("competitor-videos").getByText("3/3", { exact: true })).toBeVisible();

  // The channel can be given a name of the member's own, and the name found can be restored.
  await row.getByRole("button", { name: "Đổi tên kênh" }).click();
  await page.getByRole("textbox", { name: "Đổi tên kênh" }).or(page.locator("textarea:focus")).fill("Linh HR");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("row", { name: /Linh HR/ })).toBeVisible();
  await page.getByRole("button", { name: "Thêm thao tác với Linh HR" }).click();
  await page.getByRole("menuitem", { name: "Khôi phục tên gốc" }).click();
  await expect(page.getByRole("row", { name: /Linh Đoàn/ })).toBeVisible();

  // "Cập nhật thông tin kênh" reads only the header, and the numbers stay those of the video scan.
  await page.getByRole("button", { name: "Thêm thao tác với Linh Đoàn" }).click();
  await page.getByRole("menuitem", { name: "Cập nhật thông tin kênh" }).click();
  const refreshed = page.getByRole("row", { name: /Linh Đoàn HR/ });
  await expect(refreshed.getByText("130 N theo dõi")).toBeVisible({ timeout: 30_000 });
  await expect(refreshed.getByText("4,8 Tr", { exact: true })).toBeVisible();
});

test("without a second account saved the page asks for one and claims nothing", async ({ page }) => {
  await standIn(page, { userId: null, incognito: false });
  await loginAsSeed(page);
  await page.goto("/competitors");
  await expect(page.getByText("Chưa quét được: cần tài khoản Facebook phụ")).toBeVisible();
  await expect(page.getByRole("button", { name: "Cài đặt tài khoản phụ" })).toBeVisible();

  // Offline: the chip says so and "Quét" stays disabled.
  await expect(page.getByRole("button", { name: "Chưa kết nối tiện ích" })).toBeVisible();
  await page.getByLabel("Link Facebook của đối thủ").fill("facebook.com/linhdoan");
  await expect(page.getByRole("button", { name: /^(search )?Quét$/ })).toBeDisabled();
});

test("without the extension the page says how to install it", async ({ page }) => {
  await loginAsSeed(page);
  await page.goto("/competitors");
  await expect(page.getByText("Chưa thấy tiện ích Reels Studio")).toBeVisible();
});
