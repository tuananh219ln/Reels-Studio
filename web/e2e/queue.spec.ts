import { execFileSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { chooseOption, connectFacebook, loginAsSeed, openPublishDrawer, resetDatabase } from "./helpers";

// The api, a real worker with FFmpeg, and the fake Facebook (api/scripts/fake_services.py) all run.
test.beforeEach(() => resetDatabase());

/** "Sức khỏe" is the topic group the migrations make; its default posting times start at 07:00. */
const GROUP = "Sức khỏe";

/** The Page's "Đăng theo lịch", on its dashboard's "Lịch đăng" tab. */
async function openPage(page: Page) {
  await page.getByRole("menuitem", { name: "Quản lý kênh" }).click();
  await page.getByRole("link", { name: "Trang Dưỡng Sinh" }).click();
  await page.getByRole("tab", { name: "Lịch đăng" }).click();
  return page.getByRole("tabpanel", { name: "Lịch đăng" }).getByTestId("page-queue");
}

async function renderedVideo(page: Page) {
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("xương khớp");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page.getByTestId("scene")).toHaveCount(5, { timeout: 90_000 });
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 90_000 });
  const file = path.join(os.tmpdir(), `e2e-queue-photo-${process.pid}.jpg`);
  execFileSync("ffmpeg", [
    "-v",
    "error",
    "-y",
    "-f",
    "lavfi",
    "-i",
    "testsrc2=size=1080x1280:rate=1",
    "-frames:v",
    "1",
    file,
  ]);
  await page.getByLabel("Tải ảnh/video lên cho cảnh tiêu đề").setInputFiles(file);
  await expect(page.getByTestId("title-scene").getByTestId("scene-preview")).toBeVisible();
  const scenes = page.getByTestId("scene");
  for (let index = 0; index < (await scenes.count()); index++) {
    await scenes.nth(index).getByLabel("Tải ảnh/video lên cho cảnh", { exact: true }).setInputFiles(file);
    await expect(scenes.nth(index).getByTestId("scene-preview")).toHaveCount(1);
  }
  await page.getByTestId("render-bar").getByRole("button", { name: "Render" }).click();
  await expect(page.getByTestId("video-status")).toHaveText("Chờ đăng", { timeout: 120_000 });
}

test("a Page's owner gives it a topic group and its own posting times on Quản lý Page", async ({ page }) => {
  await loginAsSeed(page);
  await connectFacebook(page);
  const card = await openPage(page);
  await expect(card).toContainText("Chưa có giờ đăng: hãy gắn nhóm chủ đề hoặc nhập giờ riêng.");
  await expect(card).toContainText("Hàng chờ trống.");

  await chooseOption(page, card.getByLabel("Nhóm chủ đề của Trang Dưỡng Sinh"), GROUP);
  await expect(card).toContainText("Theo giờ đăng của nhóm chủ đề (giờ Việt Nam).");
  await expect(card).toContainText("Khung trống trong 48 giờ tới:");
  // Five times a day make about ten free times in 48 hours: three are named, the rest counted.
  await expect(card).toContainText(/ và \d+ khung khác\./);

  // A Page warming up posts once a day, at a time of its own.
  const times = card.getByLabel("Giờ đăng của Trang Dưỡng Sinh");
  for (const value of ["07:00", "11:30", "17:00", "21:30"]) {
    await card.locator(".ant-select-selection-item", { hasText: value }).getByLabel("close").click();
    await expect(card.locator(".ant-select-selection-item", { hasText: value })).toHaveCount(0);
  }
  await expect(times).toBeVisible();
  await expect(card).toContainText("Giờ riêng của Page (giờ Việt Nam).");

  await card.getByRole("button", { name: "Dùng giờ của nhóm" }).click();
  await expect(card).toContainText("Theo giờ đăng của nhóm chủ đề (giờ Việt Nam).");
  await expect(card.locator(".ant-select-selection-item", { hasText: "21:30" })).toHaveCount(1);

  // The member's own Pages are shown first on Quản lý Page, and their group is "của tôi" everywhere a group is picked.
  await page.getByRole("menuitem", { name: "Quản lý kênh" }).click();
  const whose = page.getByLabel("Trang nào");
  await expect(whose.getByRole("radio", { name: "Trang của tôi (1)" })).toBeChecked();
  await whose.getByText("Tất cả (1)").click();
  await expect(page.getByRole("link", { name: "Trang Dưỡng Sinh" })).toBeVisible();
  await page.getByRole("menuitem", { name: "Kho kiến thức" }).click();
  // Their group stays under the "Của tôi" filter of the group chips.
  await page
    .getByLabel("Lọc nhóm")
    .getByText(/^Của tôi/)
    .click();
  await expect(page.getByTestId("topic-list").getByRole("button", { name: new RegExp(GROUP) })).toBeVisible();
  await page.getByRole("menuitem", { name: "Video" }).click();
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await expect(dialog).toContainText(GROUP);
});

test("a rendered video added to its Page's queue is scheduled there by the worker", async ({ page }) => {
  test.setTimeout(300_000);
  await loginAsSeed(page);
  await connectFacebook(page);
  const card = await openPage(page);
  await chooseOption(page, card.getByLabel("Nhóm chủ đề của Trang Dưỡng Sinh"), GROUP);
  await expect(card).toContainText("Theo giờ đăng của nhóm chủ đề (giờ Việt Nam).");
  await page.getByRole("menuitem", { name: "Video" }).click();

  await renderedVideo(page);
  // The queue is in "Đăng bài" › Facebook; the buttons' names include their icon's label.
  await openPublishDrawer(page);
  await page.getByRole("button", { name: "unordered-list Thêm vào hàng chờ" }).click();
  const drawer = page.getByRole("dialog", { name: "Thêm vào hàng chờ" });
  await expect(drawer.getByLabel("Fanpage")).toBeVisible();
  await drawer.getByRole("button", { name: "Thêm vào hàng chờ", exact: true }).click();
  await expect(page.getByTestId("video-queue")).toContainText("của “Trang Dưỡng Sinh”");

  // The worker fills the queue once a minute and the publish job schedules the reel on Facebook.
  await expect(page.getByTestId("publication-status")).toContainText("Hẹn đăng lúc", { timeout: 150_000 });
  await expect(page.getByTestId("video-queue")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "unordered-list Thêm vào hàng chờ" })).toBeVisible();
  // "Đăng bài" is still open over the page.
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Đăng bài" })).toBeHidden();

  const after = await openPage(page);
  await expect(after).toContainText("Hàng chờ trống.");
});
