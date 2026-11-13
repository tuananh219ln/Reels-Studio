import { readFileSync } from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { expect, test } from "@playwright/test";
import { loginAsSeed, openScene, resetDatabase } from "./helpers";

/*
 * The team's Chrome extension (extension/ at the repo root, docs/decisions.md 2026-11-08). Playwright does not load
 * it: its Google page reader is run here as plain code, and the page is given a stand-in that answers the same
 * messages the extension's app.js does.
 */

test.beforeEach(() => resetDatabase());

const STOCK = "https://image.shutterstock.com/image-photo/rau-ngot-260nw-1.jpg";
// The api fetches only the public internet: this machine's address is refused, so no photo lands in E2E.
const LOCAL = "http://127.0.0.1:9/rau-ngot.jpg";

function readGoogle(html: string) {
  const context: { reelsGoogleImages?: (html: string) => { url: string; width: number; height: number }[] } = {};
  // The script sets reelsGoogleImages on its global object, which is this context.
  vm.runInNewContext(
    readFileSync(path.resolve(__dirname, "../../extension/google-results.js"), "utf-8"),
    Object.assign(context, { URL }),
  );
  return context.reelsGoogleImages!(html);
}

test("the extension reads the original photos from a Google Ảnh page and leaves Google's own out", () => {
  const html = [
    '["https://encrypted-tbn0.gstatic.com/images?q\\u003dtbn:abc",447,447]',
    '["https://product.hstatic.net/1/product/can-tay\\u003d1.jpg",1000,1000]',
    '["https://product.hstatic.net/1/product/can-tay\\u003d1.jpg",1000,1000]',
    '["https://shop.vn/nho.jpg",200,300]',
    '["https://cdn.nhathuoc.vn/a.png",949,1280]',
  ].join(",");
  expect(readGoogle(html)).toEqual([
    { url: "https://product.hstatic.net/1/product/can-tay=1.jpg", width: 1000, height: 1000 },
    { url: "https://cdn.nhathuoc.vn/a.png", width: 1280, height: 949 },
  ]);
});

test("Lấy ảnh Google: shown only with the extension, skips stock sites, and Gửi ảnh reaches its scene", async ({
  page,
}) => {
  test.setTimeout(180_000);
  // The stand-in extension: what app.js and background.js answer, with fixed results.
  await page.addInitScript(
    ({ stock, local }) => {
      const sent: { keywords?: string[]; target?: unknown } = {};
      (window as unknown as { __extension: typeof sent }).__extension = sent;
      window.addEventListener("message", (event) => {
        const data = event.data;
        if (event.source !== window || data?.source !== "reels-page") {
          return;
        }
        const answer = (body: object) => window.postMessage({ source: "reels-extension", ...body }, "*");
        if (data.type === "hello") {
          answer({ type: "ready", version: "test" });
        } else if (data.type === "find") {
          sent.keywords = data.keywords;
          const photos = [
            { url: stock, width: 900, height: 1600 },
            { url: local, width: 900, height: 1600 },
          ];
          answer({
            type: "answer",
            id: data.id,
            results: data.keywords.map((keyword: string) => ({ keyword, photos })),
          });
        } else if (data.type === "target") {
          sent.target = data.target;
        }
      });
    },
    { stock: STOCK, local: LOCAL },
  );
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("rau ngót cho người lớn tuổi");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page.getByTestId("scene")).toHaveCount(5, { timeout: 90_000 });
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 90_000 });

  // Every scene lacks a photo: one search per scene, a stock site is never even fetched.
  const picks: { url: string; auto: boolean }[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/media-from-url")) {
      picks.push(request.postDataJSON());
    }
  });
  await page.getByRole("button", { name: "Lấy ảnh Google cho cảnh thiếu ảnh" }).click();
  await expect(page.getByText(/Đã lấy ảnh Google cho 0\/6 cảnh/)).toBeVisible({ timeout: 60_000 });
  const keywords = await page.evaluate(
    () => (window as unknown as { __extension: { keywords: string[] } }).__extension.keywords,
  );
  expect(keywords).toHaveLength(6);
  expect(picks.length).toBe(12);
  expect(picks.every((pick) => pick.auto === true)).toBe(true);

  // "Tìm trên Google" tells the extension which scene "Gửi ảnh vào Reels Studio" sends to.
  await page.context().route("https://www.google.com/**", (route) => route.fulfill({ body: "Google Ảnh" }));
  const first = page.getByTestId("scene").first();
  await openScene(first);
  await first.getByRole("button", { name: "Tìm trên Google" }).click();
  const opened = page.waitForEvent("popup");
  await page.locator(".ant-dropdown:visible").getByRole("menuitem").nth(1).click();
  await (await opened).close();
  const target = await page.evaluate(
    () => (window as unknown as { __extension: { target: { sceneId: number; label: string } } }).__extension.target,
  );
  expect(target.label).toMatch(/^Cảnh “/);

  // A photo sent from Google Ảnh arrives on that scene like a pasted link (refused here, being this machine's).
  const sentLink = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith(`/scenes/${target.sceneId}/media-from-url`),
  );
  await page.evaluate(
    ({ sceneId, url }) => window.postMessage({ source: "reels-extension", type: "send-image", sceneId, url }, "*"),
    { sceneId: target.sceneId, url: LOCAL },
  );
  expect((await sentLink).postDataJSON()).toEqual({ url: LOCAL });
});

test("without the extension the video page offers no Google button", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("canxi cho người lớn tuổi");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page.getByTestId("scene")).toHaveCount(5, { timeout: 90_000 });
  await expect(page.getByRole("button", { name: "Tạo ảnh AI cho cảnh thiếu" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Lấy ảnh Google cho cảnh thiếu ảnh" })).toHaveCount(0);
});
