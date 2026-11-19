import { readFileSync } from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { expect, test, type Page } from "@playwright/test";
import { chooseOption, loginAsSeed, resetDatabase } from "./helpers";

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

type Meta = { name: string | null; followers: string | null; avatar_src: string | null };

/** Runs the extension's header reader the way Chrome does (executeScript `func`): its own source alone in the page. */
async function readMeta(page: Page): Promise<Meta> {
  const context: { reelsStudioReadMeta?: (selectors: unknown) => Promise<Meta> } = {};
  vm.runInNewContext(readFileSync(path.resolve(__dirname, "../../extension/facebook-reels.js"), "utf-8"), context);
  const selectors = JSON.parse(readFileSync(path.resolve(__dirname, "../../extension/selectors.json"), "utf-8"));
  return page.evaluate(`(${context.reelsStudioReadMeta!.toString()})(${JSON.stringify(selectors)})`) as Promise<Meta>;
}

test("the channel's name and avatar are the Page's own, never Messenger's heading or the scan account's picture", async ({
  page,
}) => {
  // A Page as Facebook draws it: the top bar with the signed-in account's picture, Messenger's panel with its own h1,
  // then the cover and the Page's avatar beside its name. Before, the first `svg image` (the account's) was taken for
  // every channel, the panel's "Đoạn chat" became a channel's name, and a helper beside the reader was not injected
  // with it, so nothing at all was read.
  await page.setContent(`
    <div role="banner"><svg width="40" height="40"><image href="https://scontent.fbcdn.net/account.jpg" width="40" height="40"/></svg></div>
    <div role="dialog"><h1>Đoạn chat</h1></div>
    <div role="main">
      <div>
        <img alt="Ảnh bìa" src="https://scontent.fbcdn.net/cover.jpg" style="width:900px;height:300px;display:block">
        <div>
          <svg width="168" height="168"><image href="https://scontent.fbcdn.net/page.jpg" width="168" height="168"/></svg>
          <div><h1>Kênh đối thủ</h1><span>262 N người theo dõi</span></div>
        </div>
      </div>
      <svg width="16" height="16"><image href="https://scontent.fbcdn.net/reaction.png" width="16" height="16"/></svg>
    </div>`);
  expect(await readMeta(page)).toMatchObject({
    name: "Kênh đối thủ",
    followers: "262 N",
    avatar_src: "https://scontent.fbcdn.net/page.jpg",
  });
  // A Page with no picture of its own gives none rather than the account's, and its name is still read.
  await page.evaluate(() => document.querySelector('[role="main"] svg')?.remove());
  expect(await readMeta(page)).toMatchObject({ name: "Kênh đối thủ", avatar_src: null });
});

test("a hidden scan window is brought back before the grid is scrolled, so it is read past 10 reels", async ({
  page,
}) => {
  // Covered by another window, the scan window is hidden to Chrome and Facebook stops loading the grid: profiles
  // stopped at 10 reels whenever the member worked elsewhere during a scan.
  await page.setContent(`<body style="margin:0">
    <div role="main"><h1>Kênh đối thủ</h1><div id="grid"></div></div>
    <script>
      let visibility = "hidden";
      Object.defineProperty(document, "visibilityState", { get: () => visibility });
      window.__show = () => { visibility = "visible"; };
      let next = 1;
      const add = () => {
        for (let i = 0; i < 10 && next <= 40; i++, next++) {
          const a = document.createElement("a");
          a.href = "/reel/" + (100000 + next) + "/";
          a.style.cssText = "display:block;height:300px";
          a.innerText = next + "K";
          document.getElementById("grid").appendChild(a);
        }
      };
      add();
      window.addEventListener("scroll", () => {
        if (visibility === "hidden") return;
        if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 50) add();
      });
    </script></body>`);
  await page.evaluate(() => {
    const shown: string[] = [];
    const runtime = {
      sendMessage: async (message: { type: string }) => {
        if (message.type === "scan-show") {
          shown.push(message.type);
          (window as unknown as { __show: () => void }).__show();
        }
      },
    };
    Object.assign(window, { __shown: shown, chrome: { runtime } });
  });
  const context: { reelsStudioScanReels?: (...args: unknown[]) => Promise<unknown> } = {};
  vm.runInNewContext(readFileSync(path.resolve(__dirname, "../../extension/facebook-reels.js"), "utf-8"), context);
  const selectors = readFileSync(path.resolve(__dirname, "../../extension/selectors.json"), "utf-8");
  const ended = await page.evaluate(`(${context.reelsStudioScanReels!.toString()})(1, 40, ${selectors}, "reel")`);
  expect(ended).toEqual({ status: "done", name: "Kênh đối thủ" });
  expect(await page.evaluate(() => document.querySelectorAll('a[href*="/reel/"]').length)).toBe(40);
  expect(await page.evaluate(() => (window as unknown as { __shown: string[] }).__shown.length)).toBe(1);
});

test("a reel's caption and posting time are its own, never Messenger's panel opened after a new sign-in", async ({
  page,
}) => {
  // After the cookies were pasted again Facebook opened Messenger's panel (no role of its own) before the page: every
  // reel got the caption "Các đoạn chat của bạn chưa được sao lưu" and a chat's "5 phút" as its posting time.
  await page.setContent(`
    <div style="position:fixed;right:0;top:0;width:300px;height:400px;background:#fff">
      <h1>Đoạn chat</h1>
      <div><span dir="auto">Các đoạn chat của bạn chưa được sao lưu</span></div>
      <a role="link" href="/messages/t/1"><span>5 phút</span></a>
      <div role="button" aria-label="Đóng" onclick="window.__closed = true">x</div>
    </div>
    <div role="main"><video></video>
      <div><span dir="auto">Mẹo ngủ ngon mỗi tối cho người lớn tuổi</span></div>
      <a role="link" href="/reel/1"><span>3 ngày</span></a>
    </div>`);
  const context: { reelsStudioReadReel?: (...args: unknown[]) => Promise<unknown> } = {};
  vm.runInNewContext(readFileSync(path.resolve(__dirname, "../../extension/facebook-reels.js"), "utf-8"), context);
  const selectors = readFileSync(path.resolve(__dirname, "../../extension/selectors.json"), "utf-8");
  const reel = await page.evaluate(`(${context.reelsStudioReadReel!.toString()})(${selectors}, false)`);
  expect(reel).toMatchObject({ caption: "Mẹo ngủ ngon mỗi tối cho người lớn tuổi", posted_raw: "3 ngày" });
  // The panel's close button was pressed.
  expect(await page.evaluate(() => (window as unknown as { __closed?: boolean }).__closed)).toBe(true);
});

test("a profile's grid in its own scrolling box is read to the end, under the Page's name", async ({ page }) => {
  // A profile (profile.php?id=…) as Facebook draws it: the reels in a box that scrolls on its own, ten more each time
  // its end is reached, and Messenger's panel with its own h1. Scrolling the window alone stopped every profile at 10
  // reels, and the panel's "Đoạn chat" was taken for the name.
  await page.setContent(`<body style="margin:0;overflow:hidden;height:100vh">
    <div role="dialog"><h1>Đoạn chat</h1></div>
    <div id="box" role="main" style="height:100vh;overflow-y:auto"><h1>Kênh đối thủ</h1><div id="grid"></div></div>
    <script>
      let next = 1;
      const add = () => {
        for (let i = 0; i < 10 && next <= 40; i++, next++) {
          const a = document.createElement("a");
          a.href = "/reel/" + (100000 + next) + "/";
          a.style.cssText = "display:block;height:300px";
          a.innerText = next + "K";
          document.getElementById("grid").appendChild(a);
        }
      };
      add();
      document.getElementById("box").addEventListener("scroll", (event) => {
        const box = event.target;
        if (box.scrollTop + box.clientHeight >= box.scrollHeight - 50) add();
      });
    </script></body>`);
  await page.evaluate(() => {
    const sent: unknown[] = [];
    Object.assign(window, { __sent: sent, chrome: { runtime: { sendMessage: async (m: unknown) => sent.push(m) } } });
  });
  const context: { reelsStudioScanReels?: (...args: unknown[]) => Promise<unknown> } = {};
  vm.runInNewContext(readFileSync(path.resolve(__dirname, "../../extension/facebook-reels.js"), "utf-8"), context);
  const selectors = readFileSync(path.resolve(__dirname, "../../extension/selectors.json"), "utf-8");
  // As Chrome runs it: the function's own source alone in the page.
  const ended = await page.evaluate(`(${context.reelsStudioScanReels!.toString()})(1, 40, ${selectors}, "reel")`);
  expect(ended).toEqual({ status: "done", name: "Kênh đối thủ" });
  const ids = await page.evaluate(() =>
    (window as unknown as { __sent: { type: string; videos?: { fb_video_id: string }[] }[] }).__sent
      .filter((message) => message.type === "scan-batch")
      .flatMap((message) => message.videos!.map((video) => video.fb_video_id)),
  );
  expect(new Set(ids).size).toBe(40);
});

type Copy = { cookies: { name: string; value: string }[]; userId: string; savedAt: string };
type Sync = { backup?: Copy; forget?: true };

/** The extension's scan-account.js against a chrome.storage.local kept in memory, as a fresh install starts. */
function extensionStore() {
  const data: Record<string, unknown> = {};
  const local = {
    get: async (key: string) => (key in data ? { [key]: data[key] } : {}),
    set: async (values: Record<string, unknown>) => Object.assign(data, values),
    remove: async (key: string) => delete data[key],
  };
  const context: {
    chrome: unknown;
    syncScanAccount?: (copy: Copy | null) => Promise<Sync>;
    saveScanAccount?: (text: string) => Promise<unknown>;
    clearScanAccount?: () => Promise<void>;
  } = { chrome: { storage: { local } } };
  vm.runInNewContext(readFileSync(path.resolve(__dirname, "../../extension/scan-account.js"), "utf-8"), context);
  return { data, sync: context.syncScanAccount!, save: context.saveScanAccount!, clear: context.clearScanAccount! };
}

test("an extension installed again takes the cookies back from the page's copy, never after Xóa", async () => {
  const copy: Copy = {
    cookies: [
      { name: "c_user", value: "100099999999999" },
      { name: "xs", value: "12:abc" },
    ],
    userId: "100099999999999",
    savedAt: "2026-11-18T15:00:00.000Z",
  };
  // Installed again: nothing saved, the page's copy is taken back and nothing more is sent to the page.
  const fresh = extensionStore();
  expect(await fresh.sync(copy)).toEqual({});
  expect(fresh.data.scanAccount).toMatchObject({ userId: "100099999999999", savedAt: copy.savedAt });

  // Cookies pasted in the extension: the page gets them for its copy, whether it had none or an older one.
  const saved = extensionStore();
  await saved.save("c_user=100088888888888; xs=9:new");
  expect((await saved.sync(null)).backup).toMatchObject({ userId: "100088888888888" });
  expect((await saved.sync(copy)).backup).toMatchObject({ userId: "100088888888888" });

  // "Xóa": the copy that predates it goes, and is not restored.
  await saved.clear();
  expect(await saved.sync(copy)).toEqual({ forget: true });
  expect(saved.data.scanAccount).toBeUndefined();

  // A copy without c_user and xs is never taken.
  const broken = extensionStore();
  expect(await broken.sync({ ...copy, cookies: [{ name: "datr", value: "x" }] })).toEqual({ forget: true });
  expect(broken.data.scanAccount).toBeUndefined();
});

test("the page keeps the extension's copy of the cookies and sends it back with each question", async ({ page }) => {
  const copy: Copy = {
    cookies: [
      { name: "c_user", value: "100099999999999" },
      { name: "xs", value: "12:abc" },
    ],
    userId: "100099999999999",
    savedAt: "2026-11-18T15:00:00.000Z",
  };
  await page.addInitScript((copy) => {
    const asked: unknown[] = [];
    (window as unknown as { __asked: unknown[] }).__asked = asked;
    window.addEventListener("message", (event) => {
      const data = event.data;
      if (event.source !== window || data?.source !== "reels-page") return;
      const answer = (body: object) => window.postMessage({ source: "reels-extension", ...body }, "*");
      if (data.type === "hello") answer({ type: "ready", version: "1.7.0" });
      if (data.type === "scan-account") {
        asked.push(data.backup ?? null);
        // The first question of the first visit gets the extension's cookies; later ones are answered plainly.
        const first = asked.length === 1 && !data.backup;
        answer({ type: "answer", id: data.id, userId: null, incognito: false, ...(first ? { backup: copy } : {}) });
      }
    });
  }, copy);
  await loginAsSeed(page);
  await page.goto("/competitors");
  await expect
    .poll(() => page.evaluate(() => JSON.parse(localStorage.getItem("reels-studio-scan-account") ?? "null")))
    .toEqual(copy);
  await page.reload();
  await expect.poll(() => page.evaluate(() => (window as unknown as { __asked: unknown[] }).__asked[0])).toEqual(copy);
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
              // The least viewed has no caption: "Clone" is off for it.
              caption: id === "1000003" ? null : `Caption của ${id}: 3 món giúp xương chắc`,
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
  await expect(page.getByRole("button", { name: "Tiện ích sẵn sàng, TK phụ …9999999" })).toBeVisible();

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
  // The per-stretch posting line ("Reels: 19/11/2026 đến 19/11/2026: —/tuần; …") is gone; "Video/tuần" stays.
  await expect(page.getByText(/ đến .*\/tuần/)).toHaveCount(0);
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

  // A column's header sorts the list like the "Sắp xếp" box, and the box follows it.
  const header = page.getByRole("columnheader", { name: /Trung vị/ });
  await expect(page.getByRole("columnheader", { name: /Tổng view/ })).toHaveAttribute("aria-sort", "descending");
  await header.click();
  await expect(header).toHaveAttribute("aria-sort", "descending");
  await expect(page).toHaveURL(/sort=median/);
  await expect(page.getByText("Sắp xếp: Trung vị")).toBeVisible();
});

test("a competitor's video is cloned into a hand-written draft that names its source", async ({ page }) => {
  await standIn(page, { userId: "100099999999999", incognito: true });
  await loginAsSeed(page);
  await page.goto("/competitors");
  await page.getByLabel("Link Facebook của đối thủ").fill("https://www.facebook.com/linhdoan");
  await page.getByRole("button", { name: /^(search )?Quét$/ }).click();
  const row = page.getByRole("row", { name: /Linh Đoàn/ });
  await expect(row.getByText("Xong", { exact: true })).toBeVisible({ timeout: 30_000 });
  await row.getByRole("button", { name: "Mở rộng Linh Đoàn" }).click();

  const videos = page.getByTestId("competitor-videos");
  // "Clone" sits by "Sao chép link"; a video without a caption cannot be cloned.
  await expect(videos.getByRole("button", { name: "Sao chép link …000001" })).toBeVisible();
  await expect(videos.getByRole("button", { name: "Clone video …000003" })).toBeDisabled();
  await videos.getByRole("button", { name: "Clone video …000001" }).click();

  const dialog = page.getByRole("dialog", { name: "Clone video" });
  await expect(dialog.getByLabel("Tiêu đề")).toHaveValue("Caption của 1000001: 3 món giúp xương chắc");
  await expect(dialog.getByTestId("clone-comments")).toHaveText("Bình luận mẫu: có 1");
  // The script is shown before anything is made, and may be edited.
  await dialog.getByLabel("Kịch bản").fill("Cảnh của tôi\nĐọc: Lời đọc của tôi");
  await chooseOption(page, dialog.getByLabel("Nhóm chủ đề"), "Sức khỏe");
  await dialog.getByRole("button", { name: "Tạo video" }).click();

  await expect(page.getByText("Đã tạo video")).toBeVisible();
  await page.getByTestId("clone-open").click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);
  const source = page.getByTestId("competitor-source");
  await expect(source.getByRole("link", { name: "Linh Đoàn" })).toHaveAttribute(
    "href",
    "https://www.facebook.com/reel/1000001/",
  );
  await source.getByText("Bình luận mẫu (1)").click();
  await expect(source.getByText("Mẹ tôi đau gối, ăn được không ạ?")).toBeVisible();
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

test("the rule for a big channel is set on Cài đặt › Phân tích đối thủ and kept", async ({ page }) => {
  await loginAsSeed(page);
  await page.goto("/settings/competitors");
  await expect(page.getByLabel("Số video đạt ngưỡng để coi là kênh lớn")).toHaveValue("10");
  await page.getByLabel("Số video đạt ngưỡng để coi là kênh lớn").fill("4");
  await page.getByRole("button", { name: "Lưu ngưỡng" }).click();
  await expect(page.getByText("Đã lưu ngưỡng kênh lớn")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Số video đạt ngưỡng để coi là kênh lớn")).toHaveValue("4");
});
