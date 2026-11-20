import { expect, test } from "@playwright/test";
import { loginAsSeed, resetDatabase } from "./helpers";

test.beforeEach(() => resetDatabase());

test("the app can be installed: manifest and icons are public and the page links them", async ({ page, request }) => {
  // Before login: the browser fetches these without a session.
  const response = await request.get("/manifest.webmanifest");
  expect(response.ok()).toBe(true);
  const manifest = await response.json();
  expect(manifest.display).toBe("standalone");
  expect(manifest.start_url).toBe("/videos");
  for (const icon of manifest.icons) {
    const file = await request.get(icon.src);
    expect(file.headers()["content-type"]).toContain("image/png");
  }
  expect((await request.get("/apple-touch-icon.png")).ok()).toBe(true);

  await page.goto("/login");
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/manifest.webmanifest");
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveCount(1);
});

test("the account menu explains how to install on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await loginAsSeed(page);
  await page.getByTestId("account").click();
  await page.getByRole("menuitem", { name: "Cài app lên điện thoại" }).click();
  const dialog = page.getByRole("dialog", { name: "Cài app lên điện thoại" });
  await expect(dialog.getByText("Thêm vào Màn hình chính").first()).toBeVisible();
  await expect(dialog.getByText("Cài đặt ứng dụng")).toBeVisible();
});
