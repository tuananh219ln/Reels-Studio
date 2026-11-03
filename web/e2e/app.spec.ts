import { readdirSync } from "node:fs";
import path from "node:path";
import { expect, test, type Browser } from "@playwright/test";
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
  await expect(page.getByText("Th 12", { exact: true })).toBeVisible();
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

test("music library page from the menu", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Thư viện nhạc" }).click();
  await expect(page).toHaveURL(/\/music$/);
  await expect(page.getByText("Chưa có bài nhạc nào")).toBeVisible();
});

test("Kết nối Fanpage opens from inside the Cài đặt menu group", async ({ page }) => {
  await loginAsSeed(page);
  const settings = page.getByRole("menuitem", { name: "Cài đặt" });
  const fanpages = page.getByRole("menuitem", { name: "Kết nối Fanpage" });
  await expect(fanpages).toBeVisible();
  await settings.click();
  await expect(fanpages).toBeHidden();
  await settings.click();
  await fanpages.click();
  await expect(page).toHaveURL(/\/fanpages$/);
  await expect(page.getByRole("button", { name: "Thêm Fanpage" })).toBeVisible();
});

test("the worker checks a connected Page's token and shows its followers", async ({ page }) => {
  await loginAsSeed(page);
  await connectFacebook(page);
  await page.getByRole("menuitem", { name: "Kết nối Fanpage" }).click();
  // The worker checks a newly connected Page within seconds; the page asks again until it has.
  await expect(page.getByText("Hoạt động", { exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("cell", { name: "1.200" })).toBeVisible();
  await page.getByRole("button", { name: "Kiểm tra ngay" }).click();
  await expect(page.getByText("Đang kiểm tra…")).toBeHidden({ timeout: 20_000 });
  await expect(page.getByText("Hoạt động", { exact: true })).toBeVisible();
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
  await page.getByRole("menuitem", { name: "Affiliate Shopee" }).click();
  await expect(page).toHaveURL(/\/affiliate$/);
  await expect(page.getByText("Chưa có video nào đã đăng")).toBeVisible();

  await page.getByRole("tab", { name: "Sản phẩm" }).click();
  await page.getByRole("button", { name: "Thêm sản phẩm" }).click();
  const dialog = page.getByRole("dialog", { name: "Thêm sản phẩm" });
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
