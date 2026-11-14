import { readdirSync } from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";
import {
  SEED,
  addUser,
  chooseOption,
  connectFacebook,
  login,
  loginAsSeed,
  openAccountMenu,
  resetDatabase,
  row,
} from "./helpers";

test.beforeEach(() => resetDatabase());

async function newPage(browser: Browser) {
  const context = await browser.newContext({ baseURL: "http://localhost:3100", locale: "vi-VN" });
  return context.newPage();
}

// Every page behind the login: each folder of src/app/(app), so a new page is checked without editing this list.
const appPages = readdirSync(path.resolve(__dirname, "../src/app/(app)"), { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => `/${entry.name}`);

for (const url of ["/", ...appPages, "/change-password"]) {
  test(`${url} redirects to login on the server when there is no session`, async ({ page }) => {
    const response = await page.goto(url);
    // A server redirect means the first request answered 307; the app page never rendered.
    expect(response?.request().redirectedFrom()?.url()).toBe(`http://localhost:3100${url}`);
    await expect(page).toHaveURL(/\/login$/);
  });
}

test("the privacy policy opens without a session, for Meta's app review, and only it", async ({ page }) => {
  const response = await page.goto("/privacy");
  expect(response?.status()).toBe(200);
  await expect(page).toHaveURL(/\/privacy$/);
  await expect(page.getByRole("heading", { name: "Chính sách quyền riêng tư", level: 1 })).toBeVisible();
  // Visitors' comments are kept (name and text), so the policy must say so.
  await expect(page.getByText("tên người bình luận và nội dung bình luận")).toBeVisible();
  // Only /privacy itself is public: a path that merely starts with it still needs the login.
  await page.goto("/privacy-x");
  await expect(page).toHaveURL(/\/login$/);
});

test("the terms of service open without a session, for Meta's app review, and only it", async ({ page }) => {
  const response = await page.goto("/terms");
  expect(response?.status()).toBe(200);
  await expect(page).toHaveURL(/\/terms$/);
  await expect(page.getByRole("heading", { name: "Điều khoản sử dụng", level: 1 })).toBeVisible();
  // The terms point to the privacy policy, which is public too.
  await page.getByRole("link", { name: "Chính sách quyền riêng tư" }).click();
  await expect(page).toHaveURL(/\/privacy$/);
  // Only /terms itself is public: a path that merely starts with it still needs the login.
  await page.goto("/terms-x");
  await expect(page).toHaveURL(/\/login$/);
});

test("last login is shown as dd/mm/yyyy hh:mm in Vietnam time whatever the browser time zone", async ({ browser }) => {
  const context = await browser.newContext({ baseURL: "http://localhost:3100", timezoneId: "America/New_York" });
  const page = await context.newPage();
  await loginAsSeed(page);
  await page.goto("/users");
  const shown = (await row(page, SEED.email).getByRole("cell").nth(4).innerText()).trim();
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Ho_Chi_Minh",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date())
      .map((p) => [p.type, p.value]),
  );
  expect(shown).toMatch(/^\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}$/);
  expect(shown.slice(0, 13)).toBe(`${parts.day}/${parts.month}/${parts.year} ${parts.hour}`);
});

test("the calendar opens on today in Vietnam whatever the browser time zone", async ({ browser }) => {
  const context = await browser.newContext({ baseURL: "http://localhost:3100", timezoneId: "America/New_York" });
  const page = await context.newPage();
  await loginAsSeed(page);
  // 30 November in New York, already 1 December in Vietnam.
  await page.clock.setFixedTime(new Date("2026-11-30T20:00:00Z"));
  await page.goto("/calendar");
  // The week holds Vietnam's today, Tuesday 1 December; the month view opens on December too.
  await expect(page.getByTestId("week-today")).toHaveAttribute("title", "2026-12-01");
  await page.getByLabel("Kiểu lịch").getByText("Tháng", { exact: true }).click();
  await expect(page.getByTestId("calendar-title")).toHaveText("Tháng 12, 2026");
  await expect(page.locator(".ant-picker-cell-today")).toHaveAttribute("title", "2026-12-01");
});

test("search box filters by email or name", async ({ page }) => {
  await loginAsSeed(page);
  await addUser(page, "binh@doi.vn", "Trần Thị Bình", "tam-thoi-123");
  await page.getByLabel("Tìm theo email hoặc tên").fill("BÌNH");
  await expect(row(page, "binh@doi.vn")).toBeVisible();
  await expect(row(page, SEED.email)).toHaveCount(0);
  await page.getByLabel("Tìm theo email hoặc tên").fill("");
  await expect(row(page, SEED.email)).toBeVisible();
});

/** "Vô hiệu hoá" on a row: the member's name is typed to confirm. */
async function disableUser(page: Page, email: string, name: string) {
  await row(page, email).getByRole("button", { name: "Vô hiệu hoá" }).click();
  const dialog = page.getByRole("dialog", { name: "Vô hiệu hoá người dùng?" });
  const ok = dialog.getByRole("button", { name: "Vô hiệu hoá" });
  await expect(ok).toBeDisabled();
  await dialog.getByLabel("Nhập tên để xác nhận").fill(name.slice(0, 3));
  await expect(ok).toBeDisabled();
  await dialog.getByLabel("Nhập tên để xác nhận").fill(name);
  await ok.click();
}

test("a refused row action shows the API message and refreshes the stale row", async ({ page, browser }) => {
  await loginAsSeed(page);
  await addUser(page, "binh@doi.vn", "Trần Thị Bình", "tam-thoi-123");
  await disableUser(page, "binh@doi.vn", "Trần Thị Bình");
  await expect(row(page, "binh@doi.vn")).toContainText("Kích hoạt lại");
  const teammate = await newPage(browser);
  await loginAsSeed(teammate);
  await teammate.goto("/users");
  await expect(row(teammate, "binh@doi.vn")).toContainText("Kích hoạt lại");
  await row(page, "binh@doi.vn").getByRole("button", { name: "Kích hoạt lại" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Kích hoạt lại" }).click();
  await expect(row(page, "binh@doi.vn")).toContainText("Hoạt động");

  // The other tab still shows Bình as disabled, where a temporary password may be set.
  await row(teammate, "binh@doi.vn").getByRole("button", { name: "Đặt mật khẩu tạm" }).click();
  const dialog = teammate.getByRole("dialog", { name: "Đặt mật khẩu tạm" });
  await dialog.getByLabel("Mật khẩu tạm").fill("tam-moi-5678");
  await dialog.getByRole("button", { name: "Lưu" }).click();
  await expect(teammate.getByText("Chỉ đặt mật khẩu tạm cho tài khoản đã vô hiệu hoá")).toBeVisible();
  await expect(row(teammate, "binh@doi.vn").getByRole("button", { name: "Đặt mật khẩu tạm" })).toBeDisabled();
});

test("login, empty video list, header and logout", async ({ page }) => {
  await login(page, SEED.email, "sai-mat-khau");
  await expect(page.locator(".ant-alert")).toHaveText("Email hoặc mật khẩu không đúng");

  await login(page, "  AN@Doi.VN ", SEED.password);
  await expect(page).toHaveURL(/\/videos$/);
  await expect(page.getByText("Chưa có video nào")).toBeVisible();
  // The empty list offers its action in place.
  await page.getByRole("button", { name: "Làm video đầu tiên" }).click();
  await expect(page.getByRole("dialog", { name: "Tạo video" })).toBeVisible();
  await page.getByRole("dialog", { name: "Tạo video" }).getByRole("button", { name: "Huỷ" }).click();
  await expect(page.getByTestId("header-name")).toHaveText(SEED.name);
  await expect(page.getByTestId("account").locator(".ant-avatar")).toHaveText("A");

  await openAccountMenu(page);
  await page.getByRole("menuitem", { name: "Đăng xuất" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/videos");
  await expect(page).toHaveURL(/\/login$/);
});

test("Tự viết: a pasted script becomes scenes at once, with no AI and a safety reminder", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByText("Tự viết", { exact: true }).click();
  await expect(dialog.getByTestId("llm-line")).toHaveCount(0);
  await expect(dialog.getByTestId("hand-written-note")).toBeVisible();
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("6 món *bổ xương*");
  await dialog
    .getByLabel("Kịch bản", { exact: true })
    .fill("Vừng đen *giàu canxi*\nĐọc: Vừng đen giàu canxi, giúp xương chắc khỏe hơn.\n\nCá hồi giảm đau khớp");
  await dialog.getByRole("button", { name: "Tạo video" }).click();

  await expect(page).toHaveURL(/\/videos\/\d+$/);
  // No job: the scenes are there at once, editable.
  await expect(page.getByTestId("scene")).toHaveCount(2);
  await expect(page.getByTestId("script-by")).toHaveText("Kịch bản tự viết, không qua AI");
  await expect(page.getByTestId("scene").first().getByLabel("Lời đọc")).toHaveValue(
    "Vừng đen giàu canxi, giúp xương chắc khỏe hơn.",
  );
  await page.getByRole("button", { name: "Thêm cảnh" }).click();
  await expect(page.getByTestId("scene")).toHaveCount(3);
  // The AI's safety review is not shown any more; a hand-written video still says it was not reviewed.
  await expect(page.getByTestId("hand-written-review")).toBeVisible();
});

test("Tạo video starts on the topic group the member last made a video in", async ({ page }) => {
  await loginAsSeed(page);
  await page.goto("/knowledge");
  await page.getByLabel("Tên nhóm chủ đề mới").fill("Vườn rau");
  await page.getByRole("button", { name: "Thêm nhóm" }).click();
  const garden = page.locator('[data-topic="Vườn rau"]');
  await garden.getByRole("tab", { name: "Prompt", exact: true }).click();
  await garden.getByLabel("Prompt viết kịch bản", { exact: true }).fill("Viết kịch bản trồng rau về [Chủ đề]");
  await garden.getByRole("button", { name: "Lưu", exact: true }).first().click();
  await expect(page.getByText("Đã lưu prompt viết kịch bản")).toBeVisible();

  // With no choice yet, the dialog starts on the first group with a prompt.
  await page.goto("/videos");
  await page.getByRole("button", { name: "Tạo video" }).click();
  let dialog = page.getByRole("dialog", { name: "Tạo video" });
  await expect(dialog.getByLabel("Nhóm chủ đề")).toBeVisible();
  await expect(dialog).toContainText("Sức khỏe");
  await chooseOption(page, dialog.getByLabel("Nhóm chủ đề"), "Vườn rau");
  await dialog.getByText("Tự viết", { exact: true }).click();
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("rau mầm");
  await dialog.getByLabel("Kịch bản", { exact: true }).fill("Rau mầm *dễ trồng*\nĐọc: Rau mầm trồng trong một tuần.");
  await dialog.getByRole("button", { name: "Tạo video" }).click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);

  // The choice is kept on the server: a fresh page (or another device) starts on it.
  await page.goto("/videos");
  await page.reload();
  await page.getByRole("button", { name: "Tạo video" }).click();
  dialog = page.getByRole("dialog", { name: "Tạo video" });
  await expect(dialog.getByLabel("Nhóm chủ đề")).toBeVisible();
  await expect(dialog).toContainText("Vườn rau");
  await expect(dialog).not.toContainText("Sức khỏe");
});

async function handWrittenVideo(page: Page, topic: string) {
  await page.goto("/videos");
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByText("Tự viết", { exact: true }).click();
  await dialog.getByLabel("Chủ đề", { exact: true }).fill(topic);
  await dialog.getByLabel("Kịch bản", { exact: true }).fill(`${topic} *dễ trồng*\nĐọc: ${topic} trồng trong một tuần.`);
  await dialog.getByRole("button", { name: "Tạo video" }).click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);
}

test("the video page shows where the video stands, step by step, with its times", async ({ page }) => {
  await loginAsSeed(page);
  await handWrittenVideo(page, "rau dền");
  await expect(page.getByTestId("video-created-at")).toHaveText(/^\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}$/);
  const progress = page.getByTestId("video-progress");
  // Written by hand a moment ago; no photo, no MP4, nothing posted, no product yet.
  await expect(progress.getByTestId("progress-script")).toHaveAttribute("data-state", "done");
  await expect(progress.getByTestId("progress-script")).toContainText(/phút trước/);
  await expect(progress.getByTestId("progress-media")).toHaveAttribute("data-state", "warn");
  await expect(progress.getByTestId("progress-media")).toContainText("0/2 cảnh");
  await expect(progress.getByTestId("progress-render")).toContainText("Chưa có MP4");
  await expect(progress.getByTestId("progress-post")).toContainText("Chưa đăng");
  await expect(progress.getByTestId("progress-affiliate")).toHaveAttribute("data-state", "warn");
  await expect(progress.getByTestId("progress-48h")).toHaveCount(0);
  // A step opens the side panel's tab where it is done.
  await progress.getByTestId("progress-affiliate").click();
  await expect(page.locator("[data-side-panel]").getByRole("tab", { name: "Đăng bài", exact: true })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.locator('[data-post-block="products"]')).toBeInViewport();
  await progress.getByTestId("progress-render").click();
  await expect(page.getByText("Sẵn sàng đăng?")).toBeVisible();
});

test("only a thing's maker is offered to delete it: a teammate sees no Xóa on the video, scene or group", async ({
  page,
  browser,
}) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await handWrittenVideo(page, "cải mầm");
  const videoUrl = page.url();
  // The maker finds "Xóa video" under "⋯", and a scene's own delete button.
  await page.getByRole("button", { name: "Thao tác khác với video" }).click();
  await expect(page.getByRole("menuitem", { name: "Xóa video" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Xóa cảnh" }).first()).toBeVisible();
  await page.goto("/knowledge");
  await page.getByLabel("Tên nhóm chủ đề mới").fill("Nhóm của An");
  await page.getByRole("button", { name: "Thêm nhóm" }).click();

  await addUser(page, "binh@doi.vn", "Trần Bình", "mat-khau-tam-1");
  const binh = await newPage(browser);
  await login(binh, "binh@doi.vn", "mat-khau-tam-1");
  await binh.getByLabel("Mật khẩu mới", { exact: true }).fill("binh-moi-1234");
  await binh.getByLabel("Nhập lại mật khẩu mới").fill("binh-moi-1234");
  await binh.getByRole("button", { name: "Lưu mật khẩu mới" }).click();
  await expect(binh).toHaveURL(/\/videos$/);

  // Bình still opens and edits An's video, but has nothing to delete it or its scenes with.
  await binh.goto(videoUrl);
  await expect(binh.getByTestId("scene").first()).toBeVisible();
  await expect(binh.getByRole("button", { name: /^(delete )?Xóa$/ })).toHaveCount(0);
  await binh.getByRole("button", { name: "Thao tác khác với video" }).click();
  await expect(binh.getByRole("menuitem", { name: "Nhân bản" })).toBeVisible();
  await expect(binh.getByRole("menuitem", { name: "Xóa video" })).toHaveCount(0);
  await binh.keyboard.press("Escape");
  await expect(binh.getByRole("button", { name: "Xóa cảnh" })).toHaveCount(0);
  // And the api refuses it if asked directly.
  const id = videoUrl.split("/").pop();
  const refused = await binh.request.delete(`/api/videos/${id}`, { headers: { Origin: new URL(binh.url()).origin } });
  expect(refused.status()).toBe(403);

  await binh.goto("/knowledge");
  // "Của tôi" is the start, and the group is An's.
  await binh
    .getByLabel("Lọc nhóm")
    .getByText(/^Cả đội/)
    .click();
  await binh.getByRole("button", { name: /Nhóm của An/ }).click();
  await binh.locator('[data-topic="Nhóm của An"]').getByRole("button", { name: "Thao tác khác với nhóm" }).click();
  await expect(binh.getByRole("menuitem", { name: "Xoá nhóm (chỉ người tạo nhóm)" })).toHaveAttribute(
    "aria-disabled",
    "true",
  );
});

test("each list starts on the member's own work, and Cả đội shows everyone's", async ({ page, browser }) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await handWrittenVideo(page, "rau mầm");
  await page.getByRole("menuitem", { name: "Bài viết" }).click();
  await page.getByRole("button", { name: "Tạo bài viết" }).click();
  const drawer = page.getByRole("dialog", { name: "Tạo bài viết" });
  await drawer.getByLabel("Chủ đề của bài").fill("ngâm chân nước gừng");
  await drawer.getByRole("button", { name: "Tạo bài" }).click();
  await expect(page).toHaveURL(/\/articles\/\d+$/);

  await addUser(page, "binh@doi.vn", "Trần Bình", "mat-khau-tam-1");
  const binh = await newPage(browser);
  await login(binh, "binh@doi.vn", "mat-khau-tam-1");
  await binh.getByLabel("Mật khẩu mới", { exact: true }).fill("binh-moi-1234");
  await binh.getByLabel("Nhập lại mật khẩu mới").fill("binh-moi-1234");
  await binh.getByRole("button", { name: "Lưu mật khẩu mới" }).click();
  await expect(binh).toHaveURL(/\/videos$/);

  // Without work of their own a list starts on everyone's, so it is never empty for a newcomer.
  await expect(binh.getByText("rau mầm")).toBeVisible();
  await binh.goto("/articles");
  const whose = binh.getByLabel("Của ai");
  await expect(whose.getByRole("radio", { name: "Cả đội (1)" })).toBeChecked();
  await expect(binh.getByText("ngâm chân nước gừng")).toBeVisible();
  await whose.getByText("Của tôi (0)").click();
  await expect(binh.getByText("ngâm chân nước gừng")).toHaveCount(0);
  await binh.goto("/posts");
  await expect(binh.getByLabel("Của ai").getByRole("radio", { name: "Cả đội (0)" })).toBeChecked();
  // Jobs are read from the api a page at a time, so they start on the member's own.
  await binh.goto("/jobs");
  await expect(binh.getByLabel("Của ai").getByRole("radio", { name: "Của tôi" })).toBeChecked();

  // Once they have made a video, the list starts on theirs; the creator filter still reaches a teammate's.
  await handWrittenVideo(binh, "cải xoăn");
  await binh.goto("/videos");
  await expect(binh.getByLabel("Người tạo")).toBeVisible();
  await expect(binh.getByText("cải xoăn")).toBeVisible();
  await expect(binh.getByText("rau mầm")).toHaveCount(0);
  await chooseOption(binh, binh.getByLabel("Người tạo"), SEED.name);
  await expect(binh.getByText("rau mầm")).toBeVisible();
  await expect(binh.getByText("cải xoăn")).toHaveCount(0);
});

test("music library page from the menu", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Thư viện nhạc" }).click();
  await expect(page).toHaveURL(/\/music$/);
  await expect(page.getByText("Chưa có bài nhạc nào")).toBeVisible();
});

test("the menu is four headed groups in the order of the work, with no Bình luận", async ({ page }) => {
  await loginAsSeed(page);
  const menu = page.getByRole("menu").first();
  for (const heading of ["Tạo nội dung", "Đăng và kiếm tiền", "Tài nguyên", "Quản trị"]) {
    await expect(menu.getByText(heading, { exact: true })).toBeVisible();
  }
  const items = await menu.getByRole("menuitem").allInnerTexts();
  expect(items.map((item) => item.trim())).toEqual([
    "Video",
    "Bài viết",
    "Bài đăng",
    "Quản lý Page",
    "Affiliate",
    "Kho kiến thức",
    "Kho tư liệu",
    "Thư viện nhạc",
    "Quản lý người dùng",
    "Nhật ký job",
    "Cài đặt",
  ]);
  const fanpages = page.getByRole("menuitem", { name: "Quản lý Page" });
  await fanpages.click();
  await expect(page.getByRole("heading", { name: "Quản lý Page" })).toBeVisible();
  await expect(page).toHaveURL(/\/fanpages$/);
  // Once the list has loaded with no Page yet, the empty state offers its own, differently named button.
  await expect(page.getByText("Chưa kết nối Fanpage nào")).toBeVisible();
  await expect(page.getByRole("button", { name: "Thêm Fanpage" })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Kết nối Page đầu tiên" })).toBeVisible();
});

test("the worker checks a connected Page's token and shows its followers", async ({ page }) => {
  await loginAsSeed(page);
  await connectFacebook(page);
  await page.getByRole("menuitem", { name: "Quản lý Page" }).click();
  const card = page.getByTestId("fanpage-card");
  // The worker checks a newly connected Page within seconds; the page asks again until it has.
  await expect(card.getByText("Hoạt động", { exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(card.getByText("1.200", { exact: true })).toBeVisible();
  await card.getByRole("button", { name: "Kiểm tra ngay" }).click();
  await expect(card.getByText("Hoạt động", { exact: true })).toBeVisible({ timeout: 20_000 });
});

test("a Page's card opens its dashboard, with a period and six tabs", async ({ page }) => {
  await loginAsSeed(page);
  await connectFacebook(page);
  await page.getByRole("menuitem", { name: "Quản lý Page" }).click();
  const card = page.getByTestId("fanpage-card").filter({ hasText: "Trang Dưỡng Sinh" });
  await expect(card.getByText("Hoạt động", { exact: true })).toBeVisible({ timeout: 20_000 });
  // The card keeps one line on posting; the whole of it is on the dashboard.
  await expect(card.getByTestId("page-schedule-line")).toHaveText(
    "Chưa gắn nhóm chủ đề, chưa có giờ đăng, 0 video trong hàng chờ",
  );
  await expect(card.getByTestId("page-queue")).toHaveCount(0);
  // A click on the card itself, not on its controls, opens the Page.
  await card.getByText("Số liệu 7 ngày", { exact: false }).click();
  await expect(page).toHaveURL(/\/fanpages\/\d+$/);
  await expect(page.getByRole("heading", { name: "Trang Dưỡng Sinh" })).toBeVisible();
  // The menu still shows where the member is.
  await expect(page.getByRole("menuitem", { name: "Quản lý Page" })).toHaveClass(/ant-menu-item-selected/);

  // Tổng quan: four figures, each against the period before, the views chart, the latest post and the token.
  await expect(page.getByTestId("figure-tile")).toHaveCount(4);
  await expect(page.getByText("so với 28 ngày trước", { exact: false }).first()).toBeVisible();
  await expect(page.getByTestId("latest-post")).toContainText("Chưa có bài nào app đăng lên Page này.");
  await expect(page.getByTestId("token-status")).toContainText("Hoạt động");
  await expect(page.getByTestId("figure-tile").filter({ hasText: "Người theo dõi mới" })).toContainText(
    "Hiện có 1.200",
  );

  // The period changes every figure.
  await page.getByText("7 ngày", { exact: true }).click();
  await expect(page.getByText("so với 7 ngày trước", { exact: false }).first()).toBeVisible();

  await page.getByRole("tab", { name: "Lượt xem" }).click();
  const views = page.getByRole("tabpanel", { name: "Lượt xem" });
  await expect(views.getByTestId("figure-tile")).toHaveCount(3);
  await expect(views.getByText("Thời gian xem TB")).toBeVisible();
  await expect(views.getByRole("switch", { name: "Hoạt động đăng" })).toBeChecked();

  await page.getByRole("tab", { name: "Tương tác" }).click();
  const engagement = page.getByRole("tabpanel", { name: "Tương tác" });
  for (const name of ["Cảm xúc", "Bình luận", "Chia sẻ"]) {
    await expect(engagement.getByTestId("figure-tile").filter({ hasText: name })).toBeVisible();
  }

  await page.getByRole("tab", { name: "Đối tượng" }).click();
  await expect(page.getByTestId("followers-now")).toHaveText("1.200");
  // Today's reading is one point of the followers chart; hovering it names the day.
  const chart = page.getByTestId("followers-chart");
  await expect(chart.getByRole("img")).toBeVisible();
  await chart.getByRole("img").hover();
  await expect(chart.getByTestId("chart-tooltip")).toBeVisible();
  await chart.getByRole("button", { name: "Xem bảng" }).click();
  await expect(chart.getByRole("cell", { name: "1.200" })).toBeVisible();

  await page.getByRole("tab", { name: "Nội dung" }).click();
  const content = page.getByRole("tabpanel", { name: "Nội dung" });
  await expect(content).toContainText("Chưa có bài nào app đăng lên Page này trong 7 ngày.");
  await expect(content.getByRole("button", { name: "Xuất CSV" })).toBeDisabled();

  await page.getByRole("tab", { name: "Lịch đăng" }).click();
  const schedule = page.getByRole("tabpanel", { name: "Lịch đăng" });
  await expect(schedule.getByTestId("page-queue")).toContainText("Hàng chờ trống.");
  await expect(schedule.getByTestId("scheduled-strip")).toContainText("Page chưa có giờ đăng");

  await page.getByRole("link", { name: "Quay lại Quản lý Page" }).click();
  await expect(page).toHaveURL(/\/fanpages$/);
});

test("a Page stopped and never posted to can be deleted", async ({ page }) => {
  await loginAsSeed(page);
  await connectFacebook(page);
  await page.getByRole("menuitem", { name: "Quản lý Page" }).click();
  await page.getByRole("button", { name: "Thao tác với Trang Dưỡng Sinh" }).click();
  await page.getByRole("menuitem", { name: "Ngừng dùng" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Ngừng dùng" }).click();
  await expect(page.getByText("Không có Fanpage nào đang dùng")).toBeVisible();
  await page.getByText("Đã ngừng dùng (1)").click();
  const stopped = page.getByTestId("stopped-fanpage");
  await expect(stopped.getByText(/chưa đăng bài nào/)).toBeVisible();
  await stopped.getByRole("button", { name: "Xóa" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Xóa" }).click();
  await expect(page.getByText("Chưa kết nối Fanpage nào")).toBeVisible();
});

test("Cài đặt holds the defaults, AI model and sources as tabs, each with its own address", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Cài đặt" }).click();
  await expect(page).toHaveURL(/\/settings\/defaults$/);
  await expect(page.getByRole("tab", { name: "Thiết lập mặc định" })).toHaveAttribute("aria-selected", "true");
  // The member's own settings first, then the team's, each group under its name; Kết nối MCP is the member's.
  const names = await page.getByRole("tab").allInnerTexts();
  expect(names.map((name) => name.split("\n")[0])).toEqual([
    "Của tôi",
    "Thiết lập mặc định",
    "Tài khoản affiliate",
    "Kết nối MCP",
    "Chung cả nhóm",
    "Mô hình AI",
    "Nguồn tư liệu",
    "Mẫu dựng",
    "Máy render",
  ]);
  await page.getByRole("tab", { name: "Kết nối MCP" }).click();
  await expect(page).toHaveURL(/\/settings\/mcp$/);
  await page.getByRole("tab", { name: "Nguồn tư liệu" }).click();
  await expect(page).toHaveURL(/\/settings\/sources$/);
  await expect(page.getByTestId("source-elevenlabs")).toBeVisible();
  // A reload stays on the same tab, and the menu keeps Cài đặt selected.
  await page.reload();
  await expect(page.getByRole("tab", { name: "Nguồn tư liệu" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("menuitem", { name: "Cài đặt" })).toHaveClass(/ant-menu-item-selected/);
  await page.getByRole("tab", { name: "Mô hình AI" }).click();
  await expect(page).toHaveURL(/\/settings\/ai$/);
});

test("Affiliate Shopee: add a product, see why it cannot be approved, fix it and approve", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Affiliate" }).click();
  await expect(page).toHaveURL(/\/affiliate$/);
  await expect(page.getByText("Chưa có video nào đã đăng")).toBeVisible();

  await page.getByRole("tab", { name: "Sản phẩm" }).click();
  await page.getByRole("button", { name: "Thêm sản phẩm" }).click();
  const adding = page.getByRole("dialog", { name: "Thêm sản phẩm" });
  // The seeded team has no Shopee App ID, so a pasted link cannot be read and the drawer says so.
  await expect(adding.getByText("Cần một tài khoản Shopee có App ID")).toBeVisible();
  await adding.getByRole("button", { name: "Nhập tay" }).click();
  // The closing drawer hands focus back to "Thêm sản phẩm", which would close a dropdown opened before that.
  await expect(adding).toBeHidden();
  const dialog = page.getByRole("dialog", { name: "Nhập tay sản phẩm" });
  await chooseOption(page, dialog.getByLabel("Nhóm chủ đề"), "Sức khỏe");
  await dialog.getByLabel("Tên sản phẩm").fill("Vừng đen rang");
  await dialog.getByLabel("Link affiliate").fill("https://s.shopee.vn/abc");
  await dialog.getByLabel("Tên shop").fill("Nhà Vừng");
  await chooseOption(page, dialog.getByLabel("Loại shop"), "Shopee Mall");
  await dialog.getByLabel("Số sao").fill("4.8");
  await dialog.getByLabel("Lượt bán").fill("50");
  await dialog.getByLabel("Giá (đ)").fill("100000");
  await dialog.getByLabel("Hoa hồng (%)").fill("10");
  await dialog.getByRole("button", { name: "Thêm" }).click();

  const product = row(page, "Vừng đen rang");
  await expect(product).toContainText("10.000đ/đơn");
  await expect(product).toContainText("Lượt bán dưới 100");
  await expect(product.getByRole("button", { name: "Duyệt" })).toBeDisabled();

  await product.getByRole("button", { name: "Sửa Vừng đen rang" }).click();
  const edit = page.getByRole("dialog", { name: "Sửa sản phẩm" });
  await edit.getByLabel("Lượt bán").fill("500");
  await edit.getByRole("button", { name: "Lưu" }).click();
  // The drawer hands focus back to "Sửa" once it has closed, which would close a dropdown opened before that.
  await expect(edit).toBeHidden();
  await product.getByRole("button", { name: "Duyệt" }).click();
  await expect(product).toContainText("Đã duyệt");

  const stages = page.getByLabel("Lọc theo trạng thái");
  await stages.getByText("Chờ duyệt (0)").click();
  await expect(page.getByText("Không có sản phẩm nào khớp")).toBeVisible();
  await expect(page.getByRole("link", { name: "Xuất CSV" })).toHaveAttribute("href", /status=draft/);
  await page
    .getByRole("navigation", { name: "Nhóm chủ đề" })
    .getByRole("button", { name: /Sức khỏe/ })
    .click();
  await expect(page.getByTestId("product-group")).toHaveText("Sức khỏe");
  await expect(page.getByRole("link", { name: "Xuất CSV" })).toHaveAttribute("href", /topic_id=\d+/);
  await stages.getByText("Tất cả (1)").click();
  await page.getByRole("tab", { name: "Video đã đăng" }).click();
  await page.getByRole("tab", { name: "Sản phẩm" }).click();
  await expect(product).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Xuất CSV" }).click();
  expect((await download).suggestedFilename()).toBe("san-pham-affiliate.csv");
});

test("Affiliate Shopee: import the file of Shopee Affiliate's Lấy link hàng loạt", async ({ page }) => {
  await loginAsSeed(page);
  await page.goto("/affiliate");
  await page.getByRole("tab", { name: "Sản phẩm" }).click();
  await page.getByRole("button", { name: "Nhập file" }).click();
  const dialog = page.getByRole("dialog", { name: "Thêm sản phẩm" });
  await chooseOption(page, dialog.getByLabel("Nhóm chủ đề"), "Sức khỏe");
  const csv =
    "Mã sản phẩm,Tên sản phẩm,Giá,Doanh thu,Tên cửa hàng,Tỉ lệ hoa hồng,Hoa hồng,Link sản phẩm,Link ưu đãi\n" +
    '45113237093,"Combo hạt giống rau mùa hè","45,0k",0,HỒNG HÀ F1 SEEDS,"2,5%",₫900,' +
    "https://shopee.vn/product/1346703635/45113237093,https://s.shopee.vn/4LKghKN3cR\n";
  await dialog.locator('input[type="file"]').setInputFiles({
    name: "lay-link-hang-loat.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  await expect(dialog.getByText("lay-link-hang-loat.csv")).toBeVisible();
  // The preview comes first and names the count on the button.
  await expect(dialog.getByTestId("import-preview")).toContainText("Mới 1");
  await dialog.getByRole("button", { name: "Nhập 1 sản phẩm" }).click();
  // Without a Shopee App ID the drawer stays open to say what is still to fill in.
  await expect(dialog.getByText("File không có số sao, lượt bán và loại shop")).toBeVisible();
  const product = row(page, "Combo hạt giống rau mùa hè");
  await expect(product).toContainText("HỒNG HÀ F1 SEEDS");
  await expect(product).toContainText("45.000đ");
  await expect(product).toContainText("1.125đ/đơn");

  // The three figures the file lacks are filled in on the row, and then it can be approved.
  await dialog.getByRole("button", { name: "Huỷ" }).click();
  // Once closed the drawer gives the focus back to "Nhập file", which would close a dropdown opened before that.
  await expect(dialog).toBeHidden();
  await expect(product.getByRole("button", { name: "Duyệt" })).toBeDisabled();
  const quick = product.getByTestId("quick-fill");
  await chooseOption(page, quick.getByLabel("Loại shop của Combo hạt giống rau mùa hè"), "Shop Yêu Thích");
  await quick.getByLabel("Số sao của Combo hạt giống rau mùa hè").fill("4.8");
  await quick.getByLabel("Lượt bán của Combo hạt giống rau mùa hè").fill("250");
  await quick.getByRole("button", { name: "Lưu" }).click();
  await expect(product).toContainText("4.8 / 250");
  await expect(product.getByTestId("quick-fill")).toHaveCount(0);
  await product.getByRole("button", { name: "Duyệt" }).click();
  await expect(product).toContainText("Đã duyệt");
});

/** One row of Shopee Affiliate's "Lấy link hàng loạt" file, without stars, sales or shop type. */
const line = (id: number, name: string) =>
  `${id},${name},"45,0k",0,Shop,"2,5%",₫900,https://shopee.vn/product/1/${id},\n`;

async function importRows(page: Page, ...rows: string[]) {
  await page.getByRole("button", { name: "Nhập file" }).click();
  const dialog = page.getByRole("dialog", { name: "Thêm sản phẩm" });
  await chooseOption(page, dialog.getByLabel("Nhóm chủ đề"), "Sức khỏe");
  const header =
    "Mã sản phẩm,Tên sản phẩm,Giá,Doanh thu,Tên cửa hàng,Tỉ lệ hoa hồng,Hoa hồng,Link sản phẩm,Link ưu đãi\n";
  await dialog.locator('input[type="file"]').setInputFiles({
    name: "lay-link-hang-loat.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(header + rows.join("")),
  });
  await expect(dialog.getByTestId("import-preview")).toContainText(`Mới ${rows.length}`);
  await dialog.getByRole("button", { name: `Nhập ${rows.length} sản phẩm` }).click();
  await expect(dialog.getByText("File không có số sao, lượt bán và loại shop")).toBeVisible();
  await dialog.getByRole("button", { name: "Huỷ" }).click();
  await expect(dialog).toBeHidden();
}

test("Affiliate: several products are ticked, then deleted or approved at once", async ({ page }) => {
  await loginAsSeed(page);
  await page.goto("/affiliate");
  await page.getByRole("tab", { name: "Sản phẩm" }).click();
  await importRows(page, line(11, "Hạt cải"), line(12, "Hạt dền"), line(13, "Hạt mồng tơi"));

  await page.getByRole("checkbox", { name: "Chọn Hạt cải" }).check();
  await page.getByRole("checkbox", { name: "Chọn Hạt dền" }).check();
  const selection = page.getByTestId("product-selection");
  await expect(selection).toContainText("Đã chọn 2 sản phẩm");
  await selection.getByRole("button", { name: "Xoá đã chọn" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Xoá" }).click();
  await expect(page.getByText("Đã xoá 2 sản phẩm")).toBeVisible();
  await expect(row(page, "Hạt cải")).toHaveCount(0);
  await expect(row(page, "Hạt dền")).toHaveCount(0);
  await expect(row(page, "Hạt mồng tơi")).toBeVisible();
  await expect(selection).toHaveCount(0);

  // Approving several at once: an ordinary shop passes, a row still missing its figures stays a draft.
  await importRows(page, line(14, "Hạt cải bẹ"));
  const filled = row(page, "Hạt mồng tơi");
  const quick = filled.getByTestId("quick-fill");
  await chooseOption(page, quick.getByLabel("Loại shop của Hạt mồng tơi"), "Shop thường");
  await quick.getByLabel("Số sao của Hạt mồng tơi").fill("4.8");
  await quick.getByLabel("Lượt bán của Hạt mồng tơi").fill("250");
  await quick.getByRole("button", { name: "Lưu" }).click();
  await expect(filled).toContainText("4.8 / 250");
  await page.getByRole("checkbox", { name: "Chọn Hạt mồng tơi" }).check();
  await page.getByRole("checkbox", { name: "Chọn Hạt cải bẹ" }).check();
  await selection.getByRole("button", { name: "Duyệt đã chọn" }).click();
  await expect(page.getByText("Đã duyệt 1 sản phẩm; 1 sản phẩm chưa đạt tiêu chí nên vẫn là nháp")).toBeVisible();
  await expect(filled).toContainText("Đã duyệt");
  await expect(row(page, "Hạt cải bẹ")).toContainText("Nháp");
});

test("a new user logs in with the temporary password and must change it", async ({ page, browser }) => {
  await loginAsSeed(page);
  await addUser(page, "binh@doi.vn", "Trần Thị Bình", "tam-thoi-123");
  await expect(row(page, "binh@doi.vn")).toContainText("Chưa đăng nhập");
  await expect(row(page, SEED.email)).toContainText("Tài khoản của bạn");

  const binh = await newPage(browser);
  await login(binh, "binh@doi.vn", "tam-thoi-123");
  await expect(binh).toHaveURL(/\/change-password$/);
  await binh.goto("/users");
  await expect(binh).toHaveURL(/\/change-password$/);

  await binh.getByLabel("Mật khẩu mới", { exact: true }).fill("ngan");
  await binh.getByLabel("Nhập lại mật khẩu mới").fill("khac");
  await binh.getByRole("button", { name: "Lưu mật khẩu mới" }).click();
  await expect(binh.getByText("Mật khẩu phải có ít nhất 8 ký tự")).toBeVisible();
  await expect(binh.getByText("Hai lần nhập mật khẩu không khớp")).toBeVisible();

  await binh.getByLabel("Mật khẩu mới", { exact: true }).fill("binh-moi-1234");
  await binh.getByLabel("Nhập lại mật khẩu mới").fill("binh-moi-1234");
  await binh.getByRole("button", { name: "Lưu mật khẩu mới" }).click();
  await expect(binh).toHaveURL(/\/videos$/);
  await expect(binh.getByTestId("account").locator(".ant-avatar")).toHaveText("B");
});

test("disable, re-enable, temporary password and sign out of all devices", async ({ page, browser }) => {
  await loginAsSeed(page);
  await addUser(page, "binh@doi.vn", "Trần Thị Bình", "tam-thoi-123");
  const binh = await newPage(browser);
  await login(binh, "binh@doi.vn", "tam-thoi-123");
  await expect(binh).toHaveURL(/\/change-password$/);

  await page.reload();
  await expect(row(page, "binh@doi.vn").getByRole("cell").nth(5)).toHaveText("1");

  // An active member's password is not reset: the button waits for the account to be disabled.
  await expect(row(page, "binh@doi.vn").getByRole("button", { name: "Đặt mật khẩu tạm" })).toBeDisabled();
  await disableUser(page, "binh@doi.vn", "Trần Thị Bình");
  await expect(row(page, "binh@doi.vn")).toContainText("Vô hiệu hoá");
  await expect(row(page, "binh@doi.vn").getByRole("button")).toHaveText(["Kích hoạt lại", "Đặt mật khẩu tạm"]);
  await expect(row(page, "binh@doi.vn").getByTestId("user-last-action")).toContainText(`Vô hiệu hoá bởi ${SEED.name}`);
  await binh.reload();
  await expect(binh).toHaveURL(/\/login$/);
  await login(binh, "binh@doi.vn", "tam-thoi-123");
  await expect(binh.locator(".ant-alert")).toHaveText("Tài khoản đã bị vô hiệu hoá");

  // Recovering the account: a temporary password while disabled, then enabled again.
  await row(page, "binh@doi.vn").getByRole("button", { name: "Đặt mật khẩu tạm" }).click();
  const dialog = page.getByRole("dialog", { name: "Đặt mật khẩu tạm" });
  await dialog.getByLabel("Mật khẩu tạm").fill("tam-moi-5678");
  await dialog.getByRole("button", { name: "Lưu" }).click();
  await expect(page.getByText("Đã đặt mật khẩu tạm")).toBeVisible();
  await row(page, "binh@doi.vn").getByRole("button", { name: "Kích hoạt lại" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Kích hoạt lại" }).click();
  await expect(row(page, "binh@doi.vn")).toContainText("Hoạt động");
  await expect(row(page, "binh@doi.vn").getByTestId("user-last-action")).toContainText(
    `Kích hoạt lại bởi ${SEED.name}`,
  );
  await login(binh, "binh@doi.vn", "tam-moi-5678");
  await expect(binh).toHaveURL(/\/change-password$/);

  await page.reload();
  await expect(row(page, "binh@doi.vn").getByRole("cell").nth(5)).toHaveText("1");
  await row(page, "binh@doi.vn").getByRole("button", { name: "Đăng xuất khỏi mọi thiết bị" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Đăng xuất" }).click();
  await expect(row(page, "binh@doi.vn").getByRole("cell").nth(5)).toHaveText("0");
  await binh.reload();
  await expect(binh).toHaveURL(/\/login$/);
});

test("rejected actions show the API message", async ({ page }) => {
  await loginAsSeed(page);
  await addUser(page, "binh@doi.vn", "Trần Thị Bình", "tam-thoi-123");
  await page.getByRole("button", { name: "Thêm người dùng" }).click();
  const dialog = page.getByRole("dialog", { name: "Thêm người dùng" });
  await dialog.getByLabel("Email").fill("BINH@doi.vn");
  await dialog.getByLabel("Tên").fill("Bình 2");
  await dialog.getByLabel("Mật khẩu tạm").fill("tam-thoi-123");
  await dialog.getByRole("button", { name: "Thêm" }).click();
  await expect(page.getByText("Email này đã có trong hệ thống")).toBeVisible();
});

test("change password and rename from the account menu", async ({ page }) => {
  await loginAsSeed(page);
  await openAccountMenu(page);
  await page.getByRole("menuitem", { name: "Sửa tên" }).click();
  const renameDialog = page.getByRole("dialog", { name: "Sửa tên" });
  await renameDialog.getByLabel("Tên").fill("   ");
  await renameDialog.getByRole("button", { name: "Lưu" }).click();
  await expect(renameDialog.getByText("Tên phải từ 1 đến 60 ký tự")).toBeVisible();
  await renameDialog.getByLabel("Tên").fill("  Lê Minh Châu ");
  await renameDialog.getByRole("button", { name: "Lưu" }).click();
  await expect(page.getByTestId("header-name")).toHaveText("Lê Minh Châu");
  await expect(page.getByTestId("account").locator(".ant-avatar")).toHaveText("C");

  await openAccountMenu(page);
  await page.getByRole("menuitem", { name: "Đổi mật khẩu" }).click();
  const dialog = page.getByRole("dialog", { name: "Đổi mật khẩu" });
  await dialog.getByLabel("Mật khẩu hiện tại").fill("sai-mat-khau");
  await dialog.getByLabel("Mật khẩu mới", { exact: true }).fill("an-moi-12345");
  await dialog.getByLabel("Nhập lại mật khẩu mới").fill("an-moi-12345");
  await dialog.getByRole("button", { name: "Lưu" }).click();
  await expect(page.getByText("Mật khẩu hiện tại không đúng")).toBeVisible();
  await dialog.getByLabel("Mật khẩu hiện tại").fill(SEED.password);
  await dialog.getByRole("button", { name: "Lưu" }).click();
  await expect(page.getByText("Đã đổi mật khẩu")).toBeVisible();

  await openAccountMenu(page);
  await page.getByRole("menuitem", { name: "Đăng xuất" }).click();
  await login(page, SEED.email, "an-moi-12345");
  await expect(page).toHaveURL(/\/videos$/);
});

test("phone width: collapsed menu and no horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await loginAsSeed(page);
  await page.goto("/users");
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.locator(".ant-layout-sider")).toHaveCount(0);
  await page.getByRole("button", { name: "Mở menu" }).click();
  await page.getByRole("menuitem", { name: "Video" }).click();
  await expect(page).toHaveURL(/\/videos$/);
  await page.goto("/users");
  await expect(page.getByRole("table")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("phone width: the calendar's month picker is on screen and the month fits without scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await loginAsSeed(page);
  await page.goto("/calendar");
  const month = page.locator(".ant-picker-calendar-month-select");
  await expect(month).toBeVisible();
  expect((await month.boundingBox())!.x + (await month.boundingBox())!.width).toBeLessThanOrEqual(390);
  const sunday = await page.getByRole("columnheader", { name: "CN" }).boundingBox();
  expect(sunday!.x + sunday!.width).toBeLessThanOrEqual(390);
});

test.describe("connection problems", () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([{ name: "reels_session", value: "bat-ky", url: "http://localhost:3100" }]);
  });

  test("api not running", async ({ page }) => {
    // What the Next.js proxy answers when nothing listens on API_URL: a 500 without our JSON body.
    await page.route("**/api/me", (route) => route.fulfill({ status: 500, body: "Internal Server Error" }));
    await page.goto("/videos");
    await expect(page.getByText("Không kết nối được máy chủ, thử lại sau")).toBeVisible();
  });

  test("database unavailable", async ({ page }) => {
    await page.route("**/api/me", (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          code: "database_unavailable",
          message: "Không kết nối được cơ sở dữ liệu, thử lại sau",
        }),
      }),
    );
    await page.goto("/videos");
    await expect(page.getByText("Không kết nối được cơ sở dữ liệu, thử lại sau")).toBeVisible();
  });
});

test("the app's own motion stops when the system asks for less motion", async ({ browser }) => {
  const durations = async (reducedMotion: "reduce" | "no-preference") => {
    const context = await browser.newContext({ baseURL: "http://localhost:3100", locale: "vi-VN", reducedMotion });
    const page = await context.newPage();
    await page.goto("/login");
    const button = page.getByRole("button", { name: "Đăng nhập" });
    await expect(button).toBeVisible();
    const antd = await button.evaluate((element) => getComputedStyle(element).transitionDuration);
    // The app's own: the arrow that turns when a scene card opens.
    await loginAsSeed(page);
    await page.getByRole("button", { name: "Tạo video" }).click();
    const dialog = page.getByRole("dialog", { name: "Tạo video" });
    await dialog.getByText("Tự viết", { exact: true }).click();
    await dialog.getByLabel("Chủ đề", { exact: true }).fill("Món ăn sáng");
    await dialog.getByLabel("Kịch bản", { exact: true }).fill("Phở bò\nĐọc: Phở bò nóng hổi.");
    await dialog.getByRole("button", { name: "Tạo video" }).click();
    const arrow = page.getByTestId("scene").first().locator(".scene-card-arrow");
    await expect(arrow).toBeVisible();
    const own = await arrow.evaluate((element) => getComputedStyle(element).transitionDuration);
    await context.close();
    return [antd, own];
  };
  const still = /^0s(, 0s)*$/;
  for (const duration of await durations("no-preference")) expect(duration).not.toMatch(still);
  for (const duration of await durations("reduce")) expect(duration).toMatch(still);
});

test("typing is not lost: closing a form or leaving a page with unsaved text asks first", async ({ page }) => {
  await loginAsSeed(page);
  const ask = page.locator(".ant-modal-confirm").filter({ hasText: "Bỏ các thay đổi chưa lưu?" });

  // A drawer with typing in it: "Huỷ" asks; "Tiếp tục sửa" keeps the text, "Bỏ thay đổi" closes it.
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByText("Tự viết", { exact: true }).click();
  const script = dialog.getByLabel("Kịch bản", { exact: true });
  await script.fill("Phở bò\nĐọc: Phở bò nóng hổi.");
  await dialog.getByRole("button", { name: "Huỷ" }).click();
  await ask.getByRole("button", { name: "Tiếp tục sửa" }).click();
  await expect(ask).toBeHidden();
  await expect(script).toHaveValue(/Phở bò/);
  // The drawer's × asks too.
  await dialog.getByRole("button", { name: "Đóng", exact: true }).click();
  await ask.getByRole("button", { name: "Bỏ thay đổi" }).click();
  await expect(dialog).toBeHidden();
  // Opened and closed without typing, it closes at once.
  await page.getByRole("button", { name: "Tạo video" }).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Huỷ" }).click();
  await expect(dialog).toBeHidden();
  await expect(ask).toHaveCount(0);

  // A page: a prompt typed but not saved asks before a menu link leaves it.
  await page.goto("/knowledge");
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const health = page.locator('[data-topic="Sức khỏe"]');
  await health.getByRole("tab", { name: "Prompt", exact: true }).click();
  await health.getByLabel("Prompt viết kịch bản", { exact: true }).fill("Viết thật ngắn về [Chủ đề]");
  const videos = page.getByRole("link", { name: "Video", exact: true });
  await videos.click();
  await ask.getByRole("button", { name: "Tiếp tục sửa" }).click();
  await expect(page).toHaveURL(/\/knowledge/);
  await expect(health.getByLabel("Prompt viết kịch bản", { exact: true })).toHaveValue("Viết thật ngắn về [Chủ đề]");
  await videos.click();
  await ask.getByRole("button", { name: "Bỏ thay đổi" }).click();
  await expect(page).toHaveURL(/\/videos$/);
});

test("a list's search, filters and tab are in the address, so a reload shows the same list", async ({ page }) => {
  await loginAsSeed(page);
  const searches = [
    ["/videos", "Tìm theo tiêu đề hoặc chủ đề"],
    ["/posts", "Tìm theo tiêu đề"],
    ["/jobs", "Tìm theo video"],
    ["/users", "Tìm theo email hoặc tên"],
    ["/music", "Tìm theo tên bài"],
    ["/affiliate", "Tìm theo tiêu đề video"],
  ] as const;
  for (const [url, label] of searches) {
    await page.goto(url);
    await page.getByLabel(label, { exact: true }).fill("phở bò");
    await expect(page).toHaveURL(/[?&]q=ph/);
    await page.reload();
    await expect(page.getByLabel(label, { exact: true })).toHaveValue("phở bò");
  }

  // A filter: the chosen status stays chosen; clearing it takes it out of the address.
  await page.goto("/videos");
  await chooseOption(page, page.getByLabel("Lọc theo trạng thái"), "Lỗi");
  await expect(page).toHaveURL(/[?&]status=failed/);
  await page.reload();
  await expect(page.getByRole("combobox", { name: "Lọc theo trạng thái" }).locator("..").locator("..")).toContainText(
    "Lỗi",
  );
  // "Của tôi / Cả đội" too: with no post of the member's it starts on "Cả đội", and a pick of "Của tôi" stays.
  await page.goto("/posts");
  const whose = page.getByRole("radiogroup", { name: "Của ai" });
  await expect(whose.getByRole("radio", { name: /^Cả đội/ })).toBeChecked();
  await whose.getByText(/^Của tôi/).click();
  await expect(page).toHaveURL(/[?&]whose=mine/);
  await page.reload();
  await expect(whose.getByRole("radio", { name: /^Của tôi/ })).toBeChecked();
  // Quản lý Page's "Trang của tôi / Tất cả" the same way: it starts on the member's own Page, and "Tất cả" stays.
  await connectFacebook(page);
  await page.goto("/fanpages");
  const pages = page.getByRole("radiogroup", { name: "Trang nào" });
  await expect(pages.getByRole("radio", { name: /^Trang của tôi/ })).toBeChecked();
  await pages.getByText(/^Tất cả/).click();
  await expect(page).toHaveURL(/[?&]whose=all/);
  await page.reload();
  await expect(pages.getByRole("radio", { name: /^Tất cả/ })).toBeChecked();
  // A tab: Affiliate opens on the one in its address, with that tab's own search.
  await page.goto("/affiliate");
  await page.getByRole("tab", { name: "Sản phẩm" }).click();
  await expect(page).toHaveURL(/[?&]tab=products/);
  await page.getByLabel("Tìm theo sản phẩm hoặc shop", { exact: true }).fill("hạt giống");
  await page.reload();
  await expect(page.getByRole("tab", { name: "Sản phẩm" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("Tìm theo sản phẩm hoặc shop", { exact: true })).toHaveValue("hạt giống");
});

test("a long table's page is in the address too, and a new filter goes back to page 1", async ({ page }) => {
  await loginAsSeed(page);
  await page.goto("/affiliate?tab=products");
  await page.getByRole("button", { name: "Nhập file" }).click();
  const dialog = page.getByRole("dialog", { name: "Thêm sản phẩm" });
  await chooseOption(page, dialog.getByLabel("Nhóm chủ đề"), "Sức khỏe");
  // 51 products: one more than a page of the table.
  const rows = Array.from({ length: 51 }, (_, index) => {
    const id = 45113237100 + index;
    return `${id},"Sản phẩm số ${index + 1}","45,0k",0,Shop thử,"2,5%",₫900,https://shopee.vn/product/1346703635/${id},https://s.shopee.vn/x${index}\n`;
  });
  await dialog.locator('input[type="file"]').setInputFiles({
    name: "lay-link-hang-loat.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Mã sản phẩm,Tên sản phẩm,Giá,Doanh thu,Tên cửa hàng,Tỉ lệ hoa hồng,Hoa hồng,Link sản phẩm,Link ưu đãi\n" +
        rows.join(""),
    ),
  });
  await dialog.getByRole("button", { name: "Nhập 51 sản phẩm" }).click();
  await expect(dialog.getByText("File không có số sao, lượt bán và loại shop")).toBeVisible();
  await dialog.getByRole("button", { name: "Huỷ" }).click();
  await expect(dialog).toBeHidden();

  const pager = page.locator(".ant-table-pagination");
  await pager.getByTitle("2", { exact: true }).click();
  await expect(page).toHaveURL(/[?&]page=2/);
  await page.reload();
  await expect(pager.locator(".ant-pagination-item-active")).toHaveText("2");
  await expect(page.getByRole("row")).toHaveCount(2); // the header and the 51st product
  // A search starts the table on page 1 again.
  await page.getByLabel("Tìm theo sản phẩm hoặc shop", { exact: true }).fill("Sản phẩm");
  await expect(page).not.toHaveURL(/[?&]page=/);
  await expect(pager.locator(".ant-pagination-item-active")).toHaveText("1");
});

test("Kho kiến thức and a Page's dashboard keep the group, tab, period and filters in the address", async ({
  page,
}) => {
  await loginAsSeed(page);
  // Kho kiến thức: the group shown and its tab come back after a reload.
  await page.goto("/knowledge");
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const health = page.locator('[data-topic="Sức khỏe"]');
  await health.getByRole("tab", { name: "Prompt", exact: true }).click();
  await expect(page).toHaveURL(/[?&]group=\d+/);
  await expect(page).toHaveURL(/[?&]tab=prompts/);
  await page.reload();
  await expect(health.getByRole("tab", { name: "Prompt", exact: true })).toHaveAttribute("aria-selected", "true");
  // The Video tab's search too; a new tab starts without it.
  await health.getByRole("tab", { name: /^Video/ }).click();
  await health.getByLabel("Tìm video của nhóm", { exact: true }).fill("canxi");
  await expect(page).toHaveURL(/[?&]q=canxi/);
  await page.reload();
  await expect(health.getByLabel("Tìm video của nhóm", { exact: true })).toHaveValue("canxi");
  await health.getByRole("tab", { name: /^Backlog/ }).click();
  await expect(page).not.toHaveURL(/[?&]q=/);
  await health.getByLabel("Tìm trong Backlog", { exact: true }).fill("ngủ");
  await page.reload();
  await expect(health.getByLabel("Tìm trong Backlog", { exact: true })).toHaveValue("ngủ");
  // "Lịch đăng" sits next to Backlog, and the video table starts with the video's id.
  await health.getByRole("tab", { name: "Lịch đăng", exact: true }).click();
  await expect(page).toHaveURL(/[?&]tab=schedule/);
  await health.getByRole("tab", { name: /^Video/ }).click();
  await expect(health.getByRole("columnheader", { name: "ID", exact: true })).toBeVisible();

  // A Page's dashboard: its period and tab.
  await connectFacebook(page);
  await page.getByRole("menuitem", { name: "Quản lý Page" }).click();
  const card = page.getByTestId("fanpage-card").filter({ hasText: "Trang Dưỡng Sinh" });
  await card.getByText("Số liệu 7 ngày", { exact: false }).click();
  await expect(page.getByRole("heading", { name: "Trang Dưỡng Sinh" })).toBeVisible();
  await page.getByText("7 ngày", { exact: true }).click();
  await page.getByRole("tab", { name: "Nội dung" }).click();
  await expect(page).toHaveURL(/[?&]days=7/);
  await expect(page).toHaveURL(/[?&]tab=content/);
  await page.reload();
  await expect(page.getByRole("tab", { name: "Nội dung" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("so với 7 ngày trước", { exact: false }).first()).toBeAttached();
});

test("phone width: the video list's filters sit behind Bộ lọc", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await loginAsSeed(page);
  await page.goto("/videos");
  // Not five selects stacked above the list: one button, with the search and sort beside it.
  await expect(page.getByLabel("Lọc theo trạng thái")).toHaveCount(0);
  await page.getByRole("button", { name: "Bộ lọc" }).click();
  const filters = page.getByRole("dialog", { name: "Bộ lọc" });
  await chooseOption(page, filters.getByLabel("Lọc theo trạng thái"), "Lỗi");
  await filters.getByRole("button", { name: /^Xem \d+ video$/ }).click();
  await expect(filters).toBeHidden();
  await expect(page.getByRole("button", { name: "Bộ lọc (1)" })).toBeVisible();
  await expect(page).toHaveURL(/[?&]status=failed/);
});

// A 1×1 PNG: the library takes it as a photo.
const PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

test("Kho tư liệu: items move between folders keeping their id, folders are renamed and deleted, and a group shows its folder", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  // The api takes a write only from the app's own origin.
  const headers = { Origin: new URL(page.url()).origin };
  const ids: number[] = [];
  for (const [name, folder] of [
    ["goi.png", "Gia goi khop"],
    ["ngu-1.png", "Gia - Giac ngu"],
    ["ngu-2.png", "Gia - Giac ngu"],
  ]) {
    const made = await page.request.post("/api/media", {
      multipart: { file: { name, mimeType: "image/png", buffer: PIXEL }, folder },
      headers,
    });
    expect(made.status()).toBe(201);
    ids.push((await made.json()).id);
  }
  const folderOf = async () =>
    Object.fromEntries(
      ((await (await page.request.get("/api/media")).json()).items as { id: number; folder: string }[]).map((item) => [
        item.id,
        item.folder,
      ]),
    );

  // One item: its card's "Chuyển thư mục", picking a folder that is there.
  await page.goto(`/media?folder=${encodeURIComponent("Gia goi khop")}`);
  await expect(page.getByTestId("media-item")).toHaveCount(1);
  await page.getByRole("button", { name: "Chuyển thư mục goi.png" }).click();
  const move = page.getByRole("dialog", { name: "Chuyển thư mục" });
  await chooseOption(page, move.getByLabel("Thư mục chuyển tới"), "Gia - Giac ngu (2)");
  await move.getByRole("button", { name: "Chuyển thư mục" }).click();
  await expect(page.getByText("Đã chuyển 1 tư liệu vào “Gia - Giac ngu”")).toBeVisible();
  await expect(page.getByTestId("media-item")).toHaveCount(0);

  // Several at once, into a folder made by typing its name.
  await page.goto(`/media?folder=${encodeURIComponent("Gia - Giac ngu")}`);
  await expect(page.getByTestId("media-item")).toHaveCount(3);
  await page.getByRole("button", { name: "Chọn tất cả" }).click();
  await expect(page.getByText("Đã chọn 3 tư liệu")).toBeVisible();
  await page.getByTestId("media-selection").getByRole("button", { name: "Chuyển thư mục" }).click();
  const batch = page.getByRole("dialog", { name: "Chuyển 3 tư liệu sang thư mục khác" });
  await batch.getByLabel("Thư mục chuyển tới").fill("Già Mà Khỏe");
  await chooseOption(page, batch.getByLabel("Thư mục chuyển tới"), "Tạo thư mục “Già Mà Khỏe”");
  await batch.getByRole("button", { name: "Chuyển thư mục" }).click();
  await expect(page.getByText("Đã chuyển 3 tư liệu vào “Già Mà Khỏe”")).toBeVisible();
  expect(await folderOf()).toEqual(Object.fromEntries(ids.map((id) => [id, "Già Mà Khỏe"])));

  // Renaming the folder: the filter follows it.
  await page.goto(`/media?folder=${encodeURIComponent("Già Mà Khỏe")}`);
  await expect(page.getByTestId("media-item")).toHaveCount(3);
  await page.getByRole("button", { name: "Đổi tên thư mục" }).click();
  const rename = page.getByRole("dialog", { name: "Đổi tên thư mục “Già Mà Khỏe”" });
  await rename.getByLabel("Tên mới").fill("Già - Dưỡng sinh");
  await rename.getByRole("button", { name: "Đổi tên thư mục" }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get("folder")).toBe("Già - Dưỡng sinh");
  await expect(page.getByTestId("media-item")).toHaveCount(3);

  // A group links the folder on its "Tư liệu" tab and shows its items.
  await page.goto("/knowledge");
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const health = page.locator('[data-topic="Sức khỏe"]');
  await health.getByRole("tab", { name: "Tư liệu", exact: true }).click();
  await health.getByRole("button", { name: "Liên kết thư mục" }).click();
  const link = page.getByRole("dialog", { name: "Liên kết thư mục cho nhóm “Sức khỏe”" });
  await chooseOption(page, link.getByLabel("Thư mục của nhóm"), "Già - Dưỡng sinh (3)");
  await link.getByRole("button", { name: "Liên kết thư mục" }).click();
  await expect(health.getByTestId("media-item")).toHaveCount(3);
  // Uploading from the tab lands in the group's folder.
  await health.getByRole("button", { name: "Tải ảnh vào thư mục này" }).click();
  await health
    .locator('input[type="file"][accept]')
    .setInputFiles({ name: "moi.png", mimeType: "image/png", buffer: PIXEL });
  await expect(health.getByTestId("media-item")).toHaveCount(4);
  await expect(health.getByRole("link", { name: "Mở trong Kho tư liệu" })).toHaveAttribute(
    "href",
    `/media?folder=${encodeURIComponent("Già - Dưỡng sinh")}`,
  );

  // Deleting the folder: every item stays, in "Không thư mục", and the group is unlinked.
  await page.goto(`/media?folder=${encodeURIComponent("Già - Dưỡng sinh")}`);
  await page.getByRole("button", { name: "Xoá thư mục" }).click();
  const confirm = page.getByRole("dialog", { name: "Xoá thư mục “Già - Dưỡng sinh”?" });
  await expect(confirm).toContainText("4 tư liệu chuyển về Không thư mục");
  await expect(confirm).toContainText("Nhóm Sức khỏe sẽ bỏ liên kết");
  await confirm.getByRole("button", { name: "Xoá thư mục" }).click();
  await expect(page.getByText("Đã xoá thư mục, 4 tư liệu về Không thư mục")).toBeVisible();
  const after = await folderOf();
  expect(Object.keys(after)).toHaveLength(4);
  expect(Object.values(after).every((folder) => folder === "")).toBe(true);
  await page.goto("/knowledge");
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  await health.getByRole("tab", { name: "Tư liệu", exact: true }).click();
  await expect(health.getByRole("button", { name: "Liên kết thư mục" })).toBeVisible();
});

test("Kho tư liệu: tags are edited on one item and on a batch, and the filter asks for every tag chosen", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  const headers = { Origin: new URL(page.url()).origin };
  for (const [name, folder, tags] of [
    ["co-sofa.png", "Già/Sofa", "xoay-co, sofa"],
    ["co-giuong.png", "Già/Ngủ", "xoay-co, phong-ngu"],
    ["vai-sofa.png", "Già/Sofa", "nhun-vai, sofa"],
  ]) {
    const made = await page.request.post("/api/media", {
      multipart: { file: { name, mimeType: "image/png", buffer: PIXEL }, folder, tags },
      headers,
    });
    expect(made.status()).toBe(201);
  }
  const cards = page.getByTestId("media-item");
  const card = (name: string) => cards.filter({ hasText: name });

  // Two tags: only the item with both; with a folder too, what is in both.
  await page.goto("/media?tags=xoay-co,sofa");
  await expect(cards).toHaveCount(1);
  await expect(card("co-sofa.png").getByTestId("media-tags")).toHaveText(/xoay-co.*sofa/);
  await page.goto(`/media?tags=xoay-co&folder=${encodeURIComponent("Già/Ngủ")}`);
  await expect(cards).toHaveCount(1);
  await expect(card("co-giuong.png")).toBeVisible();

  // One item's tags: typed with accents, kept as the library keeps them, still there after a reload.
  await page.goto("/media");
  await expect(cards).toHaveCount(3);
  await page.getByRole("button", { name: "Sửa thẻ vai-sofa.png" }).click();
  const edit = page.getByRole("dialog", { name: "Sửa thẻ “vai-sofa.png”" });
  await edit.getByLabel("Thẻ của tư liệu").fill("Buổi Tối");
  await edit.getByLabel("Thẻ của tư liệu").press("Enter");
  // The suggestions close when the dialog's title is clicked, uncovering its buttons.
  await edit.locator(".ant-modal-title").click();
  await expect(page.locator(".ant-select-dropdown:visible")).toHaveCount(0);
  await edit.getByRole("button", { name: "Sửa thẻ" }).click();
  await expect(page.getByText("Đã lưu thẻ của “vai-sofa.png”")).toBeVisible();
  await page.reload();
  await expect(card("vai-sofa.png").getByTestId("media-tags")).toContainText("buoi-toi");

  // A batch: "Thêm thẻ" then "Gỡ thẻ" on every item.
  await page.getByRole("button", { name: "Chọn tất cả" }).click();
  await page.getByTestId("media-selection").getByRole("button", { name: "Thêm thẻ" }).click();
  const add = page.getByRole("dialog", { name: "Thêm thẻ cho 3 tư liệu" });
  await add.getByLabel("Thẻ của tư liệu").fill("Ông");
  await add.getByLabel("Thẻ của tư liệu").press("Enter");
  // The suggestions close when the dialog's title is clicked, uncovering its buttons.
  await add.locator(".ant-modal-title").click();
  await expect(page.locator(".ant-select-dropdown:visible")).toHaveCount(0);
  await add.getByRole("button", { name: "Thêm thẻ" }).click();
  await expect(page.getByText("Đã thêm thẻ ở 3 tư liệu")).toBeVisible();
  await page.goto("/media?tags=ong");
  await expect(cards).toHaveCount(3);
  await page.getByRole("button", { name: "Chọn tất cả" }).click();
  await page.getByTestId("media-selection").getByRole("button", { name: "Gỡ thẻ" }).click();
  const remove = page.getByRole("dialog", { name: "Gỡ thẻ cho 3 tư liệu" });
  await chooseOption(page, remove.getByLabel("Thẻ của tư liệu"), "sofa (2)");
  // The suggestions close when the dialog's title is clicked, uncovering its buttons.
  await remove.locator(".ant-modal-title").click();
  await expect(page.locator(".ant-select-dropdown:visible")).toHaveCount(0);
  await remove.getByRole("button", { name: "Gỡ thẻ" }).click();
  await expect(page.getByText("Đã gỡ thẻ ở 2 tư liệu")).toBeVisible();
  await page.goto("/media?tags=sofa");
  await expect(page.getByText("Không có tư liệu nào khớp bộ lọc")).toBeVisible();
});

test("Kho tư liệu: folders show as a tree, a parent counts and shows everything below it, and a group links a parent", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  const headers = { Origin: new URL(page.url()).origin };
  for (const [name, folder, tags] of [
    ["goi-1.png", "Gia/Goi khop", ""],
    ["goi-2.png", "Gia/Goi khop", "sofa"],
    ["dung.png", "Gia/Thang bang", "sofa"],
    ["thang.png", "Gia/Thang bang", ""],
    ["cha.png", "Gia", ""],
    ["bep.png", "Gian/Bep", ""],
  ]) {
    const made = await page.request.post("/api/media", {
      multipart: { file: { name, mimeType: "image/png", buffer: PIXEL }, folder, tags },
      headers,
    });
    expect(made.status()).toBe(201);
  }
  const cards = page.getByTestId("media-item");
  const dropdown = page.locator(".ant-select-dropdown:visible");

  // The folders are a tree beside the grid: "Gia" counts its own item and its children's, "Gian" stays apart; closing
  // "Gia" hides them.
  await page.goto("/media");
  await expect(cards).toHaveCount(6);
  const folders = page.getByTestId("media-folders");
  const node = (title: string) =>
    folders.locator(".ant-tree-treenode").filter({ has: page.getByText(title, { exact: true }) });
  for (const title of ["Gia", "Goi khop", "Thang bang", "Gian", "Bep"]) {
    await expect(folders.getByText(title, { exact: true })).toBeVisible();
  }
  await expect(node("Gia").getByText("5", { exact: true })).toBeVisible();
  await expect(node("Goi khop").getByText("2", { exact: true })).toBeVisible();
  await node("Gia").locator(".ant-tree-switcher").first().click();
  await expect(folders.getByText("Goi khop", { exact: true })).toBeHidden();
  await expect(folders.getByText("Gian", { exact: true })).toBeVisible();
  await node("Gia").locator(".ant-tree-switcher").first().click();
  await expect(folders.getByText("Goi khop", { exact: true })).toBeVisible();

  // A parent shows everything in it and below it; a child only its own; with a tag, what is in both.
  await folders.getByText("Gia", { exact: true }).click();
  await expect(cards).toHaveCount(5);
  await expect(cards.filter({ hasText: "bep.png" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Đổi tên thư mục" })).toBeVisible();
  await folders.getByText("Thang bang", { exact: true }).click();
  await expect(cards).toHaveCount(2);
  await page.goto(`/media?folder=${encodeURIComponent("Gia/Thang bang")}&tags=sofa`);
  await expect(cards).toHaveCount(1);
  await expect(cards.filter({ hasText: "dung.png" })).toBeVisible();

  // The upload form (behind "Thêm tư liệu") has the same tree for its folder.
  await page.getByRole("button", { name: "Thêm tư liệu" }).click();
  await page.getByLabel("Thư mục", { exact: true }).click();
  await expect(dropdown.getByTitle("Gia (5)", { exact: true })).toBeVisible();
  await expect(dropdown.getByTitle("Goi khop (2)", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");

  // A group links the parent from the same tree, and its tab shows everything below it.
  await page.goto("/knowledge");
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const health = page.locator('[data-topic="Sức khỏe"]');
  await health.getByRole("tab", { name: "Tư liệu", exact: true }).click();
  await health.getByRole("button", { name: "Liên kết thư mục" }).click();
  const link = page.getByRole("dialog", { name: "Liên kết thư mục cho nhóm “Sức khỏe”" });
  await link.getByLabel("Thư mục của nhóm").click();
  await expect(dropdown.getByTitle("Thang bang (2)", { exact: true })).toBeVisible();
  await dropdown.getByTitle("Gia (5)", { exact: true }).click();
  await link.locator(".ant-modal-title").click();
  await link.getByRole("button", { name: "Liên kết thư mục" }).click();
  await expect(health.getByTestId("media-item")).toHaveCount(5);
  await expect(health.getByText("Thư mục Gia, 5 tư liệu", { exact: false })).toBeVisible();
});

test("Kho tư liệu: tiles are grouped by folder, open their numbers, and move when dropped on a folder", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  const headers = { Origin: new URL(page.url()).origin };
  for (const [name, folder] of [
    ["a.png", "Bếp"],
    ["b.png", "Bếp"],
    ["c.png", "Phòng"],
  ]) {
    const made = await page.request.post("/api/media", {
      multipart: { file: { name, mimeType: "image/png", buffer: PIXEL }, folder },
      headers,
    });
    expect(made.status()).toBe(201);
  }

  // One section per folder, each with its count; "Lưới" drops the sections.
  await page.goto("/media");
  const groups = page.getByTestId("media-group");
  await expect(groups).toHaveCount(2);
  await expect(groups.filter({ hasText: "Bếp" }).getByTestId("media-item")).toHaveCount(2);
  await page.getByLabel("Cách xếp").getByText("Lưới").click();
  await expect(groups).toHaveCount(0);
  await expect(page.getByTestId("media-item")).toHaveCount(3);

  // A tile opens its numbers: pixels and size.
  await page.getByTestId("media-item").filter({ hasText: "c.png" }).locator("img").click();
  const details = page.getByRole("dialog", { name: "c.png" });
  await expect(details.getByText("1 × 1 px")).toBeVisible();
  await expect(details.getByText("Phòng", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(details).toBeHidden();

  // Dropping a tile on a folder of the tree moves it there, keeping its id.
  await page
    .getByTestId("media-item")
    .filter({ hasText: "c.png" })
    .dragTo(page.getByTestId("media-folders").getByText("Bếp", { exact: true }));
  await expect(page.getByText("Đã chuyển 1 tư liệu vào “Bếp”")).toBeVisible();
  await page.getByTestId("media-folders").getByText("Bếp", { exact: true }).click();
  await expect(page.getByTestId("media-item")).toHaveCount(3);
});
