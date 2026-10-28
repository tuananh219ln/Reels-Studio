import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, type Page } from "@playwright/test";
import { API_PYTHON, E2E_DATABASE_URL } from "../playwright.config";

export const SEED = { email: "an@doi.vn", name: "Nguyễn Văn An", password: "mat-khau-dung-1" };

/** Migrate reels_e2e, wipe it and recreate the seed user (the script refuses any other database). */
export function resetDatabase() {
  execFileSync(API_PYTHON, [path.resolve(__dirname, "../../api/scripts/e2e_reset.py")], {
    env: { ...process.env, DATABASE_URL: E2E_DATABASE_URL },
    stdio: "inherit",
  });
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
