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
 * Opens a block of the video page's side panel by its title. "Bình luận" and "Sản phẩm Shopee" are blocks of the
 * "Bình luận & Sản phẩm" tab, always open; the rest are groups of the "Thiết lập" tab, which start closed (but for
 * "Âm thanh") and stay mounted, so a hidden field can be read but not seen or clicked.
 */
export async function openPanel(page: Page, title: string) {
  if (title === "Bình luận" || title === "Sản phẩm Shopee") {
    await sideTab(page, "Bình luận & Sản phẩm");
    return;
  }
  await openSetup(page);
  const header = page.locator(".ant-collapse-header[aria-expanded]").filter({
    has: page.locator(".ant-collapse-title").getByText(title, { exact: true }),
  });
  if ((await header.getAttribute("aria-expanded")) !== "true") await header.click();
  await expect(header).toHaveAttribute("aria-expanded", "true");
}

/** Picks a tab of the video page's side panel. */
export async function sideTab(page: Page, name: "Đăng bài" | "Bình luận & Sản phẩm" | "Thiết lập") {
  const tab = page.locator("[data-side-panel]").getByRole("tab", { name, exact: true });
  await tab.click();
  await expect(tab).toHaveAttribute("aria-selected", "true");
}

/** Back on the side panel's "Đăng bài" tab, after the video's settings. */
export async function closeSetup(page: Page) {
  await sideTab(page, "Đăng bài");
}

/** The side panel's "Thiết lập" tab: the video's own settings. */
export async function openSetup(page: Page) {
  await sideTab(page, "Thiết lập");
}

/**
 * "Tùy chọn đăng khác" in the side panel's "Thiết lập" tab: the drawer with every platform's own options (a Page's
 * queue, TikTok posted directly, a post made by hand), opened over the "Đăng bài" tab. A red QC check asks first (the
 * e2e MP4s have silent narration); the test goes on to the drawer either way.
 */
export async function openPublishDrawer(page: Page) {
  await openSetup(page);
  await page.getByTestId("setup-publish").getByRole("button", { name: "Tùy chọn đăng khác", exact: true }).click();
  const ask = page.locator(".ant-modal-confirm").filter({ hasText: "MP4 chưa đạt kiểm tra chất lượng" });
  const drawer = page.getByRole("dialog", { name: "Đăng bài" });
  await expect(ask.or(drawer).first()).toBeVisible();
  if (await ask.isVisible()) await ask.getByRole("button", { name: "Vẫn đăng" }).click();
  await expect(drawer).toBeVisible();
  await expect(page.locator("[data-side-panel]").getByRole("tab", { name: "Đăng bài", exact: true })).toHaveAttribute(
    "aria-selected",
    "true",
  );
}

/**
 * Opens a scene card on the video page if it is closed. One card is open at a time, so opening this one closes the
 * one that was open; a closed card keeps its fields, which can be read but not seen or clicked.
 */
export async function openScene(scene: Locator) {
  const toggle = scene.getByTestId("scene-toggle");
  if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
}
