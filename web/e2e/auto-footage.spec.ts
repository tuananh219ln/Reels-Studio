import { expect, test } from "@playwright/test";
import { loginAsSeed, resetDatabase } from "./helpers";

test.beforeEach(() => resetDatabase());

test("automatic footage is saved once and enables the job without pasted links", async ({ page }) => {
  await loginAsSeed(page);
  await page.goto("/settings/sources");
  const footage = page.getByRole("switch", { name: "Tự tìm và chọn clip theo kịch bản", exact: true });
  const photos = page.getByRole("switch", { name: "Tự tìm ảnh sau khi viết kịch bản", exact: true });
  await expect(footage).not.toBeChecked();
  await expect(photos).not.toBeChecked();
  await footage.click();
  await expect(footage).toBeChecked();
  await expect(photos).toBeChecked();
  await page.reload();
  await expect(footage).toBeChecked();
  await expect(page.getByTestId("auto-footage")).toContainText("tối đa 3 lượt gọi AI mỗi cảnh");
  await page.getByTestId("auto-footage").screenshot({ path: "/tmp/reels-auto-footage-settings.png" });
  await footage.click();
  await expect(footage).not.toBeChecked();
  await expect(photos).toBeChecked();
});
