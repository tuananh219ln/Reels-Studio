import { expect, test, type Browser } from "@playwright/test";
import { SEED, addUser, login, loginAsSeed, openAccountMenu, resetDatabase, row } from "./helpers";

test.beforeEach(() => resetDatabase());

async function newPage(browser: Browser) {
  const context = await browser.newContext({ baseURL: "http://localhost:3100", locale: "vi-VN" });
  return context.newPage();
}

test("app pages redirect to login before rendering when there is no session", async ({ page }) => {
  const response = await page.goto("/users");
  expect(response?.request().redirectedFrom()?.url()).toMatch(/\/users$/);
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText("Quản lý người dùng")).toHaveCount(0);
});

test("login, empty video list, header and logout", async ({ page }) => {
  await login(page, SEED.email, "sai-mat-khau");
  await expect(page.locator(".ant-alert")).toHaveText("Email hoặc mật khẩu không đúng");

  await login(page, "  AN@Doi.VN ", SEED.password);
  await expect(page).toHaveURL(/\/videos$/);
  await expect(page.getByText("Chưa có video nào")).toBeVisible();
  await expect(page.getByTestId("header-name")).toHaveText(SEED.name);
  await expect(page.locator("header .ant-avatar")).toHaveText("A");

  await openAccountMenu(page);
  await page.getByRole("menuitem", { name: "Đăng xuất" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/videos");
  await expect(page).toHaveURL(/\/login$/);
});

test("coming-soon pages from the menu", async ({ page }) => {
  await loginAsSeed(page);
  for (const [label, path] of [["Kho kiến thức", "/knowledge"], ["Thư viện nhạc", "/music"], ["Job logs", "/jobs"]]) {
    await page.getByRole("menuitem", { name: label }).click();
    await expect(page).toHaveURL(new RegExp(`${path}$`));
    await expect(page.getByText("Sắp có: chưa có dữ liệu")).toBeVisible();
  }
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
  await expect(binh.locator("header .ant-avatar")).toHaveText("B");
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
  await expect(page.locator("header .ant-avatar")).toHaveText("C");

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
