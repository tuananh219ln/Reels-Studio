import { expect, test } from "@playwright/test";
import { loginAsSeed, resetDatabase } from "./helpers";

// The api, a real worker with FFmpeg, and fake Claude/Pixabay (api/scripts/fake_services.py) all run.
test.beforeEach(() => resetDatabase());

test("topic to MP4: script, edits, another photo, render, play, seek and download", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề").fill("xương khớp sau 50 tuổi");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);

  // The page follows the job by itself: no reload.
  const scenes = page.getByTestId("scene");
  await expect(scenes).toHaveCount(5, { timeout: 90_000 });
  const title = page.getByTestId("title-scene");
  await expect(title.getByTestId("scene-preview")).toBeVisible();
  await expect(page.getByTestId("self-review")).toBeVisible();
  await expect(page.getByLabel("Gợi ý nhạc")).toHaveValue("Windy Hill\nMorning Coffee");

  // The choice is saved first, then shown as selected.
  await page.getByRole("radio", { name: /^6 MÓN/ }).click();
  await expect(page.getByRole("radio", { name: /^6 MÓN/ })).toBeChecked();
  await expect(title.getByLabel("Chữ trên màn hình")).toHaveValue(/^6 MÓN/);

  const first = scenes.first();
  const text = first.getByLabel("Chữ trên màn hình");
  await text.fill("Cá nhỏ chiên\nGiàu *canxi*");
  await text.blur();
  await expect(first.getByText("Đã lưu")).toBeVisible();

  const before = await first.getByTestId("scene-preview").getAttribute("src");
  await first.getByRole("button", { name: "Tìm lại ảnh" }).click();
  await expect(first.getByTestId("scene-preview")).not.toHaveAttribute("src", before ?? "");

  await page.reload();
  await expect(page.getByTestId("scene").first().getByLabel("Chữ trên màn hình")).toHaveValue(
    "Cá nhỏ chiên\nGiàu *canxi*",
  );

  await page.getByRole("button", { name: "Render" }).click();
  await expect(page.getByTestId("video-status")).toHaveText("Xong", { timeout: 120_000 });
  await expect(page.getByTestId("render-time")).toContainText("Dài 8.0 giây");

  // Seeking needs Range answers (206) through the web app's /api proxy.
  const src = await page.getByTestId("mp4-player").getAttribute("src");
  const range = await page.request.get(src ?? "", { headers: { Range: "bytes=100-199" } });
  expect(range.status()).toBe(206);
  expect((await range.body()).length).toBe(100);
  const download = await page.request.get((await page.getByRole("link", { name: "Tải MP4" }).getAttribute("href")) ?? "");
  expect(download.status()).toBe(200);
  expect(download.headers()["content-type"]).toBe("video/mp4");
  expect(download.headers()["content-disposition"]).toContain("attachment");

  await page.goto("/videos");
  const card = page.getByTestId("video-card").first();
  await expect(card.getByTestId("video-status")).toHaveText("Xong");
  await expect(card.locator("img")).toBeVisible();
  await expect(card).toContainText("6 MÓN");
});

test("after a render, editing a scene text marks the MP4 outdated", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  await page.getByRole("dialog", { name: "Tạo video" }).getByLabel("Chủ đề").fill("tim mạch");
  await page.getByRole("dialog", { name: "Tạo video" }).getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page.getByTestId("scene")).toHaveCount(5, { timeout: 90_000 });
  await page.getByRole("button", { name: "Render" }).click();
  await expect(page.getByTestId("video-status")).toHaveText("Xong", { timeout: 120_000 });

  const caption = page.getByLabel("Caption");
  await caption.fill("Caption mới");
  await caption.blur();
  await expect(page.getByText("Đã lưu")).toBeVisible();
  await expect(page.getByText("MP4 chưa cập nhật theo bản sửa")).toHaveCount(0);

  const text = page.getByTestId("scene").nth(1).getByLabel("Chữ trên màn hình");
  await text.fill("Sữa chua\nThêm *đạm*");
  await text.blur();
  await expect(page.getByText("MP4 chưa cập nhật theo bản sửa")).toBeVisible();
});

test("knowledge page edits the script prompt and banned words, and restores the default", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Kho kiến thức" }).click();
  const prompt = page.getByLabel("Prompt viết kịch bản");
  await expect(prompt).toHaveValue(/Chủ đề: \[Chủ đề\]/);

  await prompt.fill("   ");
  await expect(page.getByRole("button", { name: "Lưu prompt" })).toBeDisabled();
  await prompt.fill("Prompt mới cho [Chủ đề]");
  await page.getByRole("button", { name: "Lưu prompt" }).click();
  await expect(page.getByText("Đã lưu prompt viết kịch bản")).toBeVisible();
  await page.getByLabel("Từ cấm").fill("thần dược\nđặc trị");
  await page.getByRole("button", { name: "Lưu từ cấm" }).click();
  await expect(page.getByText("Đã lưu danh sách từ cấm")).toBeVisible();

  await page.reload();
  await expect(prompt).toHaveValue("Prompt mới cho [Chủ đề]");
  await expect(page.getByLabel("Từ cấm")).toHaveValue("thần dược\nđặc trị");

  await page.getByRole("button", { name: "Khôi phục mặc định" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Khôi phục" }).click();
  await expect(prompt).toHaveValue(/^Bạn là biên tập viên kênh Reels dưỡng sinh cho người 40\+\./);
});
