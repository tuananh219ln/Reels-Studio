import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, type Locator, type Page } from "@playwright/test";
import { API_PYTHON, E2E_DATABASE_URL } from "../playwright.config";

export const SEED = { email: "an@doi.vn", name: "Nguyễn Văn An", password: "mat-khau-dung-1" };

/** Migrate reels_e2e, wipe it and recreate the seed user (the script refuses any other database). */
export function resetDatabase() {
  execFileSync(API_PYTHON, [path.resolve(__dirname, "../../api/scripts/e2e_reset.py")], {
    env: { ...process.env, DATABASE_URL: E2E_DATABASE_URL },
    stdio: "inherit",
  });
}

/** Connects the fake Facebook Page (api/scripts/fake_services.py). */
export async function connectFacebook(page: Page) {
  await page.getByRole("menuitem", { name: "Quản lý Page" }).click();
  // The header button is always there; with no Page yet the empty state adds a second one once the list loads.
  await page.getByRole("button", { name: "Thêm Fanpage" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Thêm Fanpage" });
  await dialog.getByLabel("Token", { exact: true }).fill("fake-facebook-user-token");
  await dialog.getByRole("button", { name: "Kiểm tra token" }).click();
  // The token manages one Page, so it is already ticked.
  await expect(dialog.getByRole("checkbox", { name: /Trang Dưỡng Sinh/ })).toBeChecked();
  await dialog.getByRole("button", { name: "Lưu" }).click();
  const card = page.getByTestId("fanpage-card").filter({ hasText: "Trang Dưỡng Sinh" });
  await expect(card.getByText("ID 1234567, token …oken")).toBeVisible();
  await page.getByRole("menuitem", { name: "Video" }).click();
}

export async function login(page: Page, email = SEED.email, password = SEED.password) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mật khẩu").fill(password);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
}

export async function loginAsSeed(page: Page) {
  await login(page);
  await expect(page).toHaveURL(/\/videos$/);
}

export async function addUser(page: Page, email: string, name: string, password: string) {
  await page.goto("/users");
  await page.getByRole("button", { name: "Thêm người dùng" }).click();
  const dialog = page.getByRole("dialog", { name: "Thêm người dùng" });
  await dialog.getByLabel("Email").fill(email);
  await dialog.getByLabel("Tên").fill(name);
  await dialog.getByLabel("Mật khẩu tạm").fill(password);
  await dialog.getByRole("button", { name: "Thêm" }).click();
  await expect(page.getByRole("row", { name: new RegExp(email) })).toBeVisible();
}

export function row(page: Page, email: string) {
  return page.getByRole("row", { name: new RegExp(email.replace(".", "\\.")) });
}

export async function openAccountMenu(page: Page) {
  await page.getByTestId("header-name").click();
}

/** Picks an option of an antd Select. The option is clicked only once its dropdown has finished opening:
 * a click during the opening animation can be lost on a slow machine. */
export async function chooseOption(page: Page, select: Locator, option: string) {
  await select.click();
  const item = page.getByTitle(option, { exact: true });
  const dropdown = page.locator(".ant-select-dropdown:visible", { has: item });
  await expect(dropdown).toBeVisible();
  await expect(dropdown).not.toHaveClass(/-(appear|enter|leave)/);
  await dropdown.getByTitle(option, { exact: true }).click();
}

/**
 * Opens a panel of the video page's side tabs ("Nhạc nền", "Bình luận"…) by its title, if it is closed. The panels
 * start closed (but for "Âm thanh") and stay mounted, so a hidden field can be read but not seen or clicked.
 */
export async function openPanel(page: Page, title: string) {
  const header = page.locator(".ant-collapse-header[aria-expanded]").filter({
    has: page.locator(".ant-collapse-title").getByText(title, { exact: true }),
  });
  if ((await header.getAttribute("aria-expanded")) !== "true") await header.click();
  await expect(header).toHaveAttribute("aria-expanded", "true");
}

/**
 * "Đăng bài" on the video page. A red QC check asks first (the e2e MP4s have silent narration); the test goes on to
 * the drawer either way.
 */
export async function openPublishDrawer(page: Page) {
  // The button's name includes its icon's label.
  await page.getByRole("button", { name: "send Đăng bài", exact: true }).click();
  const ask = page.locator(".ant-modal-confirm").filter({ hasText: "MP4 chưa đạt kiểm tra chất lượng" });
  const drawer = page.getByRole("dialog", { name: "Đăng bài" });
  await expect(ask.or(drawer).first()).toBeVisible();
  if (await ask.isVisible()) await ask.getByRole("button", { name: "Vẫn đăng" }).click();
  await expect(drawer).toBeVisible();
}
