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

test("a refused row action shows the API message and refreshes the stale row", async ({ page, browser }) => {
  await loginAsSeed(page);
  await addUser(page, "binh@doi.vn", "Trần Thị Bình", "tam-thoi-123");
  const teammate = await newPage(browser);
  await loginAsSeed(teammate);
  await teammate.goto("/users");
  await row(teammate, "binh@doi.vn").getByRole("button", { name: "Vô hiệu hoá" }).click();
  await teammate.getByRole("dialog").getByRole("button", { name: "Vô hiệu hoá" }).click();
  await expect(row(teammate, "binh@doi.vn")).toContainText("Kích hoạt lại");

  // This tab still shows Bình as active.
  await row(page, "binh@doi.vn").getByRole("button", { name: "Đặt mật khẩu tạm" }).click();
  const dialog = page.getByRole("dialog", { name: "Đặt mật khẩu tạm" });
  await dialog.getByLabel("Mật khẩu tạm").fill("tam-moi-5678");
  await dialog.getByRole("button", { name: "Lưu" }).click();
  await expect(page.getByText("Hãy kích hoạt lại người dùng trước")).toBeVisible();
  await expect(row(page, "binh@doi.vn").getByRole("button")).toHaveText(["Kích hoạt lại"]);
});

test("login, empty video list, header and logout", async ({ page }) => {
  await login(page, SEED.email, "sai-mat-khau");
  await expect(page.locator(".ant-alert")).toHaveText("Email hoặc mật khẩu không đúng");

  await login(page, "  AN@Doi.VN ", SEED.password);
  await expect(page).toHaveURL(/\/videos$/);
  await expect(page.getByText("Chưa có video nào")).toBeVisible();
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
  await page.getByRole("tab", { name: "Nội dung đăng" }).click();
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

test("only a thing's maker is offered to delete it: a teammate sees no Xóa on the video, scene or group", async ({
  page,
  browser,
}) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await handWrittenVideo(page, "cải mầm");
  const videoUrl = page.url();
  await expect(page.getByRole("button", { name: /Xóa$/ }).first()).toBeVisible();
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
  await expect(binh.getByRole("button", { name: "Xóa cảnh" })).toHaveCount(0);
  // And the api refuses it if asked directly.
  const id = videoUrl.split("/").pop();
  const refused = await binh.request.delete(`/api/videos/${id}`, { headers: { Origin: new URL(binh.url()).origin } });
  expect(refused.status()).toBe(403);

  await binh.goto("/knowledge");
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
  // Jobs and comments are read from the api a page at a time, so they start on the member's own.
  await binh.goto("/jobs");
  await expect(binh.getByLabel("Của ai").getByRole("radio", { name: "Của tôi" })).toBeChecked();
  await binh.goto("/comments");
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

test("Quản lý Page opens from the menu, outside the Cài đặt group", async ({ page }) => {
  await loginAsSeed(page);
  const settings = page.getByRole("menuitem", { name: "Cài đặt" });
  const fanpages = page.getByRole("menuitem", { name: "Quản lý Page" });
  await expect(fanpages).toBeVisible();
  // Folding Cài đặt away leaves it in the menu: it is no longer a setting.
  await settings.click();
  await expect(page.getByRole("menuitem", { name: "Cấu hình" })).toBeHidden();
  await expect(fanpages).toBeVisible();
  await fanpages.click();
  await expect(page.getByRole("heading", { name: "Quản lý Page" })).toBeVisible();
  await expect(page).toHaveURL(/\/fanpages$/);
  // Once the list has loaded with no Page yet, "Thêm Fanpage" is both in the header and in the empty state.
  await expect(page.getByText("Chưa kết nối Fanpage nào")).toBeVisible();
  await expect(page.getByRole("button", { name: "Thêm Fanpage" })).toHaveCount(2);
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

test("Bình luận opens from the Đăng bài menu and starts empty", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Bình luận" }).click();
  await expect(page).toHaveURL(/\/comments$/);
  await expect(page.getByText("Không còn bình luận nào chờ trả lời")).toBeVisible();
  await page.getByText("Tất cả", { exact: true }).click();
  await expect(page.getByText("Chưa có bình luận nào")).toBeVisible();
  await page.getByRole("button", { name: "Tải bình luận mới" }).click();
  await expect(page.getByText("Đã nhờ worker tải bình luận mới", { exact: false })).toBeVisible();
});

test("Cấu hình holds the defaults, AI model and sources as tabs, each with its own address", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Cấu hình" }).click();
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
  // A reload stays on the same tab, and the menu keeps Cấu hình selected.
  await page.reload();
  await expect(page.getByRole("tab", { name: "Nguồn tư liệu" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("menuitem", { name: "Cấu hình" })).toHaveClass(/ant-menu-item-selected/);
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

  await chooseOption(page, page.getByLabel("Lọc theo trạng thái"), "Nháp");
  await expect(page.getByText("Chưa có sản phẩm nào")).toBeVisible();
  await expect(page.getByRole("link", { name: "Xuất CSV" })).toHaveAttribute("href", /status=draft/);
  await chooseOption(page, page.getByLabel("Lọc theo nhóm chủ đề"), "Sức khỏe");
  await expect(page.getByRole("link", { name: "Xuất CSV" })).toHaveAttribute("href", /topic_id=\d+/);
  await page.getByLabel("Lọc theo trạng thái").press("Escape");
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
  await dialog.getByRole("button", { name: "Nhập", exact: true }).click();
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
  await dialog.getByRole("button", { name: "Nhập", exact: true }).click();
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

  await row(page, "binh@doi.vn").getByRole("button", { name: "Vô hiệu hoá" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Vô hiệu hoá" }).click();
  await expect(row(page, "binh@doi.vn")).toContainText("Vô hiệu hoá");
  await expect(row(page, "binh@doi.vn").getByRole("button")).toHaveText(["Kích hoạt lại"]);
  await binh.reload();
  await expect(binh).toHaveURL(/\/login$/);
  await login(binh, "binh@doi.vn", "tam-thoi-123");
  await expect(binh.locator(".ant-alert")).toHaveText("Tài khoản đã bị vô hiệu hoá");

  await row(page, "binh@doi.vn").getByRole("button", { name: "Kích hoạt lại" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Kích hoạt lại" }).click();
  await expect(row(page, "binh@doi.vn")).toContainText("Hoạt động");

  await row(page, "binh@doi.vn").getByRole("button", { name: "Đặt mật khẩu tạm" }).click();
  const dialog = page.getByRole("dialog", { name: "Đặt mật khẩu tạm" });
  await dialog.getByLabel("Mật khẩu tạm").fill("tam-moi-5678");
  await dialog.getByRole("button", { name: "Lưu" }).click();
  await expect(page.getByText("Đã đặt mật khẩu tạm")).toBeVisible();
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
