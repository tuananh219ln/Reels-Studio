import { execFileSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { SEED, addUser, chooseOption, connectFacebook, login, loginAsSeed, resetDatabase } from "./helpers";

// The api, a real worker with FFmpeg, and fake Claude/stock sources (api/scripts/fake_services.py) all run.
test.beforeEach(() => resetDatabase());

test("topic to MP4: script, edits, render, play, seek, download and post", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  await connectFacebook(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("xương khớp sau 50 tuổi");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);

  // The page follows the job by itself: no reload.
  const scenes = page.getByTestId("scene");
  await expect(scenes).toHaveCount(5, { timeout: 90_000 });
  const title = page.getByTestId("title-scene");
  // No automatic photo: every scene waits for the member's own.
  await expect(title.getByTestId("scene-no-preview")).toContainText("Chưa có ảnh");
  // A video never rendered opens ready to edit.
  await expect(page.getByTestId("editing-tag")).toBeVisible();
  await expect(page.getByRole("button", { name: "Xong" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Render" })).toBeDisabled();
  await uploadPhotos(page);
  await expect(title.getByTestId("scene-preview")).toBeVisible();
  // Before an MP4 the side panel opens on "Thiết lập"; the post texts have their own tab.
  await expect(page.getByRole("tab", { name: "Thiết lập" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Nội dung đăng" }).click();
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

  // The script's photo keywords are shown for the stock search; the uploaded photo stays until replaced.
  await expect(first.getByTestId("scene-preview")).toBeVisible();
  await expect(first.getByLabel("Từ khóa tìm ảnh")).toHaveValue("cá nhỏ, món ăn");

  await page.reload();
  await expect(page.getByTestId("scene").first().getByLabel("Chữ trên màn hình")).toHaveValue(
    "Cá nhỏ chiên\nGiàu *canxi*",
  );

  await expect(first.getByText("Đọc chữ trên màn hình trước, rồi đến lời đọc")).toBeVisible();

  await page.getByRole("button", { name: "Render" }).click();
  await expect(page.getByTestId("video-status")).toHaveText("Xong", { timeout: 120_000 });
  // Each scene is lengthened to fit its fake narration of 0.3 s per word, on-screen text included, plus 0.6 s and the
  // MP3 padding: title 15 words 5.2 s, first scene 9 words 3.4 s, the other four 8 words 3.1 s each.
  await expect(page.getByTestId("render-time")).toContainText("Dài 21.0 giây");
  await expect(first.getByTestId("voice-player")).toBeVisible();

  // The tab the member picked stays picked after the render; the MP4 is under "Xuất bản".
  await page.getByRole("tab", { name: "Xuất bản" }).click();
  // Seeking needs Range answers (206) through the web app's /api proxy.
  const src = await page.getByTestId("mp4-player").getAttribute("src");
  const range = await page.request.get(src ?? "", { headers: { Range: "bytes=100-199" } });
  expect(range.status()).toBe(206);
  expect((await range.body()).length).toBe(100);
  const download = await page.request.get(
    (await page.getByRole("link", { name: "Tải MP4" }).getAttribute("href")) ?? "",
  );
  expect(download.status()).toBe(200);
  expect(download.headers()["content-type"]).toBe("video/mp4");
  expect(download.headers()["content-disposition"]).toContain("attachment");

  await page.getByRole("button", { name: "Đăng lên Facebook" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Đăng", exact: true }).click();
  await expect(page.getByTestId("publication-status")).toHaveText("Đã đăng lên Facebook", { timeout: 30_000 });
  await expect(page.getByRole("link", { name: "Xem Reel" })).toHaveAttribute("href", /facebook\.com\/reel\//);

  await page.goto("/videos");
  const card = page.getByTestId("video-card").first();
  await expect(card.getByTestId("video-status")).toHaveText("Xong");
  await expect(card.locator("img")).toBeVisible();
  await expect(card).toContainText("6 MÓN");
});

test("after a render, editing a scene text marks the MP4 outdated", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  await connectFacebook(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  await page.getByRole("dialog", { name: "Tạo video" }).getByLabel("Chủ đề", { exact: true }).fill("tim mạch");
  await page.getByRole("dialog", { name: "Tạo video" }).getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page.getByTestId("scene")).toHaveCount(5, { timeout: 90_000 });
  await uploadPhotos(page);
  await page.getByRole("button", { name: "Render" }).click();
  await expect(page.getByTestId("video-status")).toHaveText("Xong", { timeout: 120_000 });

  // datetime-local takes the browser's local time.
  const later = new Date(Date.now() + 2 * 3600 * 1000);
  later.setMinutes(later.getMinutes() - later.getTimezoneOffset());
  await page.getByRole("radio", { name: "Hẹn giờ" }).click();
  await page.getByLabel("Giờ đăng").fill(later.toISOString().slice(0, 16));
  await page.getByRole("button", { name: "Đăng lên Facebook" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Đăng", exact: true }).click();
  await expect(page.getByTestId("publication-status")).toContainText("Đã hẹn đăng lúc", { timeout: 30_000 });

  // Opened again, a rendered video is in view mode: scenes closed, nothing to change by a stray click.
  await page.reload();
  await expect(page.getByRole("button", { name: "Chỉnh sửa" })).toBeVisible();
  await expect(page.getByTestId("editing-tag")).toHaveCount(0);
  const second = page.getByTestId("scene").nth(1);
  await expect(second.getByTestId("scene-toggle")).toHaveAttribute("aria-expanded", "false");
  await expect(second.getByLabel("Chữ trên màn hình")).toHaveAttribute("readonly", "");
  await expect(page.getByRole("button", { name: "Thêm cảnh" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Render" })).toBeEnabled();

  // The post texts stay editable in view mode, and do not outdate the MP4.
  await page.getByRole("tab", { name: "Nội dung đăng" }).click();
  const caption = page.getByLabel("Caption");
  await caption.fill("Caption mới");
  await caption.blur();
  await expect(page.getByText("Đã lưu")).toBeVisible();
  await expect(page.getByText("MP4 chưa cập nhật theo bản sửa")).toHaveCount(0);

  await page.getByRole("button", { name: "Chỉnh sửa" }).click();
  await expect(page.getByTestId("editing-tag")).toBeVisible();
  await second.getByTestId("scene-toggle").click();
  const text = second.getByLabel("Chữ trên màn hình");
  await text.fill("Sữa chua\nThêm *đạm*");
  // "Xong" saves the field being typed in, then locks the page again.
  await page.getByRole("button", { name: "Xong" }).click();
  await expect(page.getByText("MP4 chưa cập nhật theo bản sửa")).toBeVisible();
  await expect(page.getByRole("button", { name: "Chỉnh sửa" })).toBeVisible();
  await expect(text).toHaveAttribute("readonly", "");
  await expect(text).toHaveValue("Sữa chua\nThêm *đạm*");
});

test("knowledge topics: each opens from its line, keeps its own texts, and an empty one cannot make a video", async ({
  page,
}) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Kho kiến thức" }).click();
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const health = page.locator('[data-topic="Sức khỏe"]');
  const scriptCard = health.locator(".ant-card").filter({ hasText: "Prompt viết kịch bản" });
  const cloneCard = health.locator(".ant-card").filter({ hasText: "Prompt nhân bản" });
  const prompt = health.getByLabel("Prompt viết kịch bản", { exact: true });
  const clonePrompt = health.getByLabel("Prompt nhân bản", { exact: true });
  await expect(prompt).toHaveValue(/Chủ đề: \[Chủ đề\]/);
  await expect(clonePrompt).toHaveValue(/^Video gốc: "\[tiêu đề\]"/);

  await prompt.fill("   ");
  await expect(scriptCard.getByRole("button", { name: "Lưu", exact: true })).toBeDisabled();
  await prompt.fill("Prompt mới cho [Chủ đề]");
  // Unsaved text in another box survives this save.
  await clonePrompt.fill("Biến thể của [tiêu đề] chưa lưu");
  await scriptCard.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(page.getByText("Đã lưu prompt viết kịch bản")).toBeVisible();
  await expect(clonePrompt).toHaveValue("Biến thể của [tiêu đề] chưa lưu");
  await cloneCard.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(page.getByText("Đã lưu prompt nhân bản")).toBeVisible();
  await health.getByLabel("Từ cấm").fill("thần dược\nđặc trị");
  await health.getByRole("button", { name: "Lưu từ cấm" }).click();
  await expect(page.getByText("Đã lưu danh sách từ cấm")).toBeVisible();

  await page.getByLabel("Tên nhóm chủ đề mới").fill("Làm đẹp");
  await page.getByRole("button", { name: "Thêm nhóm" }).click();
  await page.getByRole("button", { name: /Làm đẹp/ }).click();
  const beauty = page.locator('[data-topic="Làm đẹp"]');
  await expect(beauty.getByLabel("Prompt viết kịch bản", { exact: true })).toHaveValue("");
  await expect(beauty.getByLabel("Từ cấm")).toHaveValue("");
  await expect(prompt).toHaveValue("Prompt mới cho [Chủ đề]");

  await page.goto("/videos");
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Nhóm chủ đề").click();
  await expect(page.getByTitle("Làm đẹp (chưa có prompt)")).toHaveClass(/disabled/);
  await page.keyboard.press("Escape");
  await dialog.getByRole("button", { name: "Huỷ" }).click();

  await page.goto("/knowledge");
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  await expect(prompt).toHaveValue("Prompt mới cho [Chủ đề]");
  await expect(clonePrompt).toHaveValue("Biến thể của [tiêu đề] chưa lưu");
  await expect(health.getByLabel("Từ cấm")).toHaveValue("thần dược\nđặc trị");
  await scriptCard.getByRole("button", { name: "Khôi phục mặc định" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Khôi phục" }).click();
  await expect(prompt).toHaveValue(/^Bạn là biên tập viên kênh Reels dưỡng sinh cho người 40\+\./);
  await expect(clonePrompt).toHaveValue("Biến thể của [tiêu đề] chưa lưu");
  await expect(page.getByRole("dialog")).toBeHidden();

  await page.getByRole("button", { name: /Làm đẹp/ }).click();
  await beauty.getByRole("button", { name: "Xoá nhóm" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Xoá" }).click();
  await expect(page.getByRole("button", { name: /Làm đẹp/ })).toHaveCount(0);
});

async function newVideoWithScript(page: Page, topic: string) {
  await page.goto("/videos");
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill(topic);
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await jobFinished(page);
  await uploadPhotos(page);
}

test("video list: status and creator filters, grid or list view remembered", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "canxi cho người lớn tuổi");
  await page.goto("/videos");
  const cards = page.getByTestId("video-card");
  await expect(cards).toHaveCount(1);

  // A draft is under "Nháp", not under "Xong"; "Của tôi" keeps the member's own videos.
  await chooseOption(page, page.getByLabel("Lọc theo trạng thái"), "Xong");
  await expect(cards).toHaveCount(0);
  await expect(page.getByText("Không có video nào khớp")).toBeVisible();
  await chooseOption(page, page.getByLabel("Lọc theo trạng thái"), "Nháp");
  await expect(cards).toHaveCount(1);
  await page.getByText("Của tôi", { exact: true }).click();
  await expect(cards).toHaveCount(1);

  // The list view shows one row per video; the choice is remembered in this browser.
  await page.getByTitle("Dạng danh sách").click();
  await expect(page.getByTestId("video-row")).toHaveCount(1);
  await page.reload();
  await expect(page.getByTestId("video-row")).toHaveCount(1);
  await page.getByTestId("video-row").first().click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);
  await page.goto("/videos");
  await page.getByTitle("Dạng lưới").click();
  await expect(cards).toHaveCount(1);
});

test("phone width: the editor title keeps the full width and the actions sit below it", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await loginAsSeed(page);
  await newVideoWithScript(page, "xương khớp sau 50 tuổi");
  const title = await page.getByTestId("video-title").boundingBox();
  const render = await page.getByRole("button", { name: "Render" }).boundingBox();
  // Before the fix the actions kept their row and squeezed the title to one letter per line.
  expect(title!.width).toBeGreaterThan(300);
  expect(render!.y).toBeGreaterThan(title!.y + title!.height - 1);
  // A scene photo stays a thumbnail, not a full-screen-tall frame.
  const preview = await page.getByTestId("title-scene").getByTestId("scene-preview").boundingBox();
  expect(preview!.height).toBeLessThan(420);
  // "Render" stays on screen at the bottom, at the top of the page and deep among the scenes alike.
  await expect(page.getByRole("button", { name: "Render" })).toBeInViewport();
  await page.getByTestId("scene").nth(3).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "Render" })).toBeInViewport();
});

test("the render bar counts what blocks the render and jumps to it", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("xương khớp sau 50 tuổi");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await jobFinished(page);
  // No scene has a photo yet: each of the title and the five scenes is blocked.
  const bar = page.getByTestId("render-bar");
  await expect(bar.getByRole("button", { name: /^Còn 6 lỗi cần sửa/ })).toBeVisible();
  // A closed scene opens to show its reason.
  await page.getByRole("button", { name: "Thu gọn tất cả" }).click();
  await bar.getByRole("button", { name: /^Còn 6 lỗi cần sửa/ }).click();
  await expect(page.getByTestId("title-scene").getByTestId("scene-blocking")).toBeInViewport();
  await uploadPhotos(page);
  await expect(bar).toContainText("Sẵn sàng render.");
  await expect(bar.getByRole("button", { name: "Render" })).toBeEnabled();
});

test("scene cards open and close, count words, and crop a photo to 9:16", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "canh rau cho người lớn tuổi");
  const scenes = page.getByTestId("scene");
  const first = scenes.first();
  const toggle = first.getByTestId("scene-toggle");

  // A draft opens with every scene open; a closed one sums itself up in its title row.
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(first.getByTestId("scene-summary")).toBeVisible();
  await expect(first.getByLabel("Chữ trên màn hình")).toBeHidden();
  await page.getByRole("button", { name: "Mở tất cả" }).click();
  await expect(page.getByTestId("scene-toggle").and(page.locator('[aria-expanded="false"]'))).toHaveCount(0);
  await page.getByRole("button", { name: "Thu gọn tất cả" }).click();
  await expect(page.getByTestId("scene-toggle").and(page.locator('[aria-expanded="true"]'))).toHaveCount(0);
  await toggle.click();

  // Words are counted without the red-word stars; above the script's 10 a yellow note says so, and it still saves.
  const text = first.getByLabel("Chữ trên màn hình");
  await text.fill("Một hai ba bốn năm sáu bảy tám chín *mười* thêm");
  // The first counter is the on-screen text's; the voice text has its own.
  await expect(first.getByTestId("word-count").first()).toHaveText("11 từ · nên tối đa 10 từ");
  await text.blur();
  await expect(first.getByText("Đã lưu")).toBeVisible();

  // "Chỉnh khung": the photo turned and cropped in the browser replaces the scene's photo.
  const before = await first.getByTestId("scene-preview").getAttribute("src");
  await first.getByRole("button", { name: "Chỉnh khung" }).click();
  const crop = page.getByRole("dialog", { name: "Chỉnh khung ảnh cảnh" });
  await crop.getByRole("button", { name: "Xoay 90°" }).click();
  await crop.getByRole("button", { name: "Lật ngang" }).click();
  await crop.getByRole("button", { name: "Áp dụng" }).click();
  await expect(crop).toHaveCount(0);
  await expect(first.getByTestId("scene-preview")).not.toHaveAttribute("src", before ?? "");
});

test("preview before a render: plays scene by scene, starts from a chosen scene, shows the safe zone", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau củ cho người cao tuổi");
  await page.getByTestId("render-bar").getByRole("button", { name: "Xem trước" }).click();
  let preview = page.getByRole("dialog", { name: "Xem trước video" });
  const now = preview.getByTestId("preview-scene");
  await expect(now).toContainText("Cảnh tiêu đề");
  // The Reels frame is drawn over the video by default; the template's safe zone is off until asked for.
  await expect(preview.getByTestId("platform-frame")).toHaveAttribute("data-platform", "reels");
  await expect(preview.getByTestId("preview-safe-zone")).toHaveCount(0);
  // It moves on by itself once a scene's seconds are up.
  await expect(now).toContainText("Cảnh 1", { timeout: 20_000 });
  await preview.getByRole("button", { name: "Cảnh sau" }).click();
  await expect(now).toContainText("Cảnh 2");
  await preview.getByRole("button", { name: "Tạm dừng" }).click();
  await expect(preview.getByRole("button", { name: "Tiếp tục" })).toBeVisible();
  await preview.getByRole("switch", { name: "Vùng an toàn" }).click();
  await expect(preview.getByTestId("preview-safe-zone")).toBeVisible();
  await preview.getByText("TikTok", { exact: true }).click();
  await expect(preview.getByTestId("platform-frame")).toHaveAttribute("data-platform", "tiktok");
  await preview.getByText("Không", { exact: true }).click();
  await expect(preview.getByTestId("platform-frame")).toHaveCount(0);
  // A scene segment of the timeline jumps to that scene.
  await preview.getByRole("button", { name: "Xem Cảnh 4" }).click();
  await expect(now).toContainText("Cảnh 4");
  await page.keyboard.press("Escape");
  await expect(preview).toHaveCount(0);

  await page.getByTestId("scene").nth(2).getByRole("button", { name: "Xem từ cảnh này" }).click();
  preview = page.getByRole("dialog", { name: "Xem trước video" });
  await expect(preview.getByTestId("preview-scene")).toContainText("Cảnh 3");
  // The frame chosen last time is remembered in this browser.
  await expect(preview.getByTestId("platform-frame")).toHaveCount(0);

  // "Tạo giọng thật": ElevenLabs (the fake) reads the scenes without narration, after a confirmation.
  const voiceBox = preview.getByTestId("preview-voice");
  await expect(voiceBox).toContainText("chưa có giọng ElevenLabs");
  await voiceBox.getByRole("button", { name: "Tạo giọng thật (ElevenLabs)" }).click();
  await page.getByRole("button", { name: "Tạo giọng", exact: true }).click();
  // Once every scene has its narration, the section goes away.
  await expect(voiceBox).toHaveCount(0, { timeout: 60_000 });
});

/** A rendered video with its Page connected, open on its own page. */
async function renderedVideo(page: Page) {
  await loginAsSeed(page);
  await connectFacebook(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  await page.getByRole("dialog", { name: "Tạo video" }).getByLabel("Chủ đề", { exact: true }).fill("xương khớp");
  await page.getByRole("dialog", { name: "Tạo video" }).getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page.getByTestId("scene")).toHaveCount(5, { timeout: 90_000 });
  await jobFinished(page);
  await uploadPhotos(page);
  await page.getByRole("button", { name: "Render" }).click();
  await expect(page.getByTestId("video-status")).toHaveText("Xong", { timeout: 120_000 });
}

async function confirmPost(page: Page) {
  await page.getByRole("button", { name: "Đăng lên Facebook" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Đăng", exact: true }).click();
}

test("a posted video appears in Bài đăng and Lịch đăng bài", async ({ page }) => {
  test.setTimeout(240_000);
  await renderedVideo(page);
  await confirmPost(page);
  await expect(page.getByTestId("publication-status")).toHaveText("Đã đăng lên Facebook", { timeout: 30_000 });

  await page.getByRole("menuitem", { name: "Bài đăng" }).click();
  await expect(page).toHaveURL(/\/posts$/);
  await expect(page.getByRole("cell", { name: "Đã đăng", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Xem Reel" })).toBeVisible();
  // The status filter: a published reel is not among the scheduled ones.
  await page.getByText("Đã hẹn lịch", { exact: true }).click();
  await expect(page.getByRole("link", { name: "Xem Reel" })).toHaveCount(0);
  await page.getByText("Tất cả", { exact: true }).click();
  await expect(page.getByRole("link", { name: "Xem Reel" })).toBeVisible();

  await page.getByRole("menuitem", { name: "Lịch đăng bài" }).click();
  await expect(page).toHaveURL(/\/calendar$/);
  await expect(page.getByRole("columnheader", { name: "T2" })).toBeVisible();
  await page.locator(".ant-picker-cell-in-view a[href^='/videos/']").click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);

  // A phone shows the compact month with a dot, and today's posts listed under it.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/calendar");
  await expect(page.locator(".ant-picker-cell-today [data-testid='calendar-dot']")).toBeVisible();
  await page.locator("a[href^='/videos/']").click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);
});

test("a scheduled video appears in Bài đăng and Lịch đăng bài without a link to the reel", async ({ page }) => {
  test.setTimeout(240_000);
  await renderedVideo(page);
  await page.getByLabel("Hẹn giờ").check();
  const when = new Date(Date.now() + 60 * 60 * 1000);
  const local = new Date(when.getTime() - when.getTimezoneOffset() * 60 * 1000).toISOString().slice(0, 16);
  await page.getByLabel("Giờ đăng").fill(local);
  await confirmPost(page);
  await expect(page.getByTestId("publication-status")).toContainText("Đã hẹn đăng lúc", { timeout: 30_000 });

  await page.getByRole("menuitem", { name: "Bài đăng" }).click();
  await expect(page.getByRole("cell", { name: "Đã hẹn lịch" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Xem Reel" })).toHaveCount(0);

  await page.getByRole("menuitem", { name: "Lịch đăng bài" }).click();
  // Any cell of the grid: an hour ahead can already be tomorrow, or next month.
  await page.locator(".ant-picker-cell a[href^='/videos/']").click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);
});

test("a posted reel takes an approved product and its link goes in the pinned comment", async ({ page, context }) => {
  test.setTimeout(240_000);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await renderedVideo(page);
  await confirmPost(page);
  await expect(page.getByTestId("publication-status")).toHaveText("Đã đăng lên Facebook", { timeout: 30_000 });

  // Through the browser's fetch, so the request carries the Origin the CSRF guard wants.
  await page.evaluate(async () => {
    const send = (path: string, method = "GET", body?: unknown) =>
      fetch(`/api/affiliate-products${path}`, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      }).then((response) => response.json());
    const { topics } = await send("/options");
    const fields = {
      knowledge_topic_id: topics[0].id,
      shop_name: "Nhà Vừng",
      shop_type: "mall",
      rating: 4.8,
      sold: 500,
      price: 100000,
      commission_rate: 10,
    };
    const sesame = await send("", "POST", { ...fields, name: "Vừng đen rang", url: "https://s.shopee.vn/vung" });
    const tea = await send("", "POST", { ...fields, name: "Trà sen", url: "https://s.shopee.vn/tra", price: 50000 });
    await send(`/${sesame.id}/approve`, "POST");
    await send(`/${tea.id}/approve`, "POST");
  });

  await page.getByRole("menuitem", { name: "Affiliate Shopee" }).click();
  const picker = page.getByLabel(/^Sản phẩm của video/);
  await chooseOption(page, picker, "Vừng đen rang (~10.000đ)");
  await expect(page.getByRole("button", { name: "Sao chép" })).toBeVisible();
  await page.keyboard.press("Escape");
  await chooseOption(page, picker, "Trà sen (~5.000đ)");
  await page.keyboard.press("Escape");
  await page.reload();

  const copied = async () => {
    await page.getByRole("button", { name: "Sao chép" }).click();
    return page.evaluate(() => navigator.clipboard.readText());
  };
  // The script's sentence first, then one line per product. The Windows clipboard turns \n into \r\n.
  const both = (await copied()).split(/\r?\n/);
  expect(both[0]).toBe("Link sản phẩm ở đây nhé");
  expect(both.slice(1).sort()).toEqual(["Trà sen: https://s.shopee.vn/tra", "Vừng đen rang: https://s.shopee.vn/vung"]);

  // A product that lost its approval stays on the reel with a warning, but its link is not copied.
  await page.getByRole("tab", { name: "Sản phẩm" }).click();
  await page
    .getByRole("row", { name: /Trà sen/ })
    .getByRole("button", { name: "Bỏ duyệt" })
    .click();
  await expect(page.getByRole("row", { name: /Trà sen/ }).getByRole("button", { name: "Duyệt" })).toBeVisible();
  await page.getByRole("tab", { name: "Video đã đăng" }).click();
  await expect(page.getByText("Đã bỏ duyệt: Trà sen")).toBeVisible();
  const rest = await copied();
  expect(rest).toContain("Vừng đen rang: https://s.shopee.vn/vung");
  expect(rest).not.toContain("https://s.shopee.vn/tra");
});

/** Gives the title and every content scene a photo, as a member does after the script is written. */
async function uploadPhotos(page: Page) {
  const file = path.join(os.tmpdir(), `e2e-photo-${process.pid}.jpg`);
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
    await expect(scenes.nth(index).getByTestId("scene-preview")).toBeVisible();
  }
}

/** Scenes appear when the script is saved; the job then still assigns photos until this banner goes. */
async function jobFinished(page: Page) {
  await expect(page.getByTestId("scene")).toHaveCount(5, { timeout: 90_000 });
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 90_000 });
}

function makeMp3(): string {
  const file = path.join(os.tmpdir(), `e2e-tone-${process.pid}.mp3`);
  execFileSync("ffmpeg", [
    "-v",
    "error",
    "-y",
    "-f",
    "lavfi",
    "-i",
    "sine=frequency=440:duration=3",
    "-ac",
    "2",
    "-c:a",
    "libmp3lame",
    "-b:a",
    "96k",
    file,
  ]);
  return file;
}

test("photos from the stock picker: pick from the grid for the title and a scene, find one for another", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("canxi cho người lớn tuổi");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await jobFinished(page);
  const render = page.getByRole("button", { name: "Render" });
  await expect(render).toBeDisabled();

  // The title scene: the grid opens on its first keyword and shows every result as a large-enough thumbnail.
  const title = page.getByTestId("title-scene");
  await title.getByRole("button", { name: "Chọn từ kho ảnh" }).click();
  let picker = page.getByRole("dialog", { name: "Chọn từ kho ảnh" });
  await expect(picker.getByLabel("Từ khóa tìm ảnh")).toHaveValue("calcium rich food");
  await expect(picker.getByTestId("stock-hit")).toHaveCount(3);
  // Measured once the dialog's opening zoom has finished.
  await expect
    .poll(async () => (await picker.getByTestId("stock-hit").first().boundingBox())?.width)
    .toBeGreaterThanOrEqual(140);
  const chosen = page.waitForRequest((request) => request.method() === "POST" && /\/stock$/.test(request.url()));
  await picker.getByTestId("stock-hit").nth(1).click();
  // The full-size address goes back with the source and the keyword it was found with.
  const body = (await chosen).postDataJSON() as { source: string; keyword: string; url: string };
  expect(body.source).toBe("pixabay");
  expect(body.keyword).toBe("calcium rich food");
  expect(body.url).toMatch(/\/img\/\w+\.jpg$/);
  await expect(picker).toBeHidden();
  // The chosen photo is served by the app, not linked from Pixabay.
  await expect(title.getByTestId("scene-preview")).toHaveAttribute("src", /^\/api\/scenes\/\d+\/preview\.jpg/);
  await expect(title.getByRole("button", { name: "Tìm ảnh (Pixabay)" })).toBeVisible();

  // A content scene: a new keyword searches again, and the keyword that found the photo is kept first.
  const scenes = page.getByTestId("scene");
  const first = scenes.nth(0);
  await first.getByRole("button", { name: "Chọn từ kho ảnh" }).click();
  picker = page.getByRole("dialog", { name: "Chọn từ kho ảnh" });
  await expect(picker.getByLabel("Từ khóa tìm ảnh")).toHaveValue("small fried fish");
  const firstResult = picker.getByTestId("stock-hit").first().locator("img");
  await expect(firstResult).toBeVisible();
  const oldThumbnail = await firstResult.getAttribute("src");
  await picker.getByLabel("Từ khóa tìm ảnh").fill("cá cơm chiên");
  await picker.getByLabel("Từ khóa tìm ảnh").press("Enter");
  // The fake returns different photos per keyword: wait for the new keyword's results before choosing.
  await expect(firstResult).not.toHaveAttribute("src", oldThumbnail ?? "");
  await picker.getByTestId("stock-hit").nth(2).click();
  await expect(picker).toBeHidden();
  await expect(first.getByTestId("scene-preview")).toBeVisible();
  // The typed keyword was searched on Pixabay, so it now leads the English list (not shown on the
  // card); the card's field is the Vietnamese list, unchanged.
  await expect(first.getByLabel("Từ khóa tìm ảnh")).toHaveValue("cá nhỏ, món ăn");

  // "Tìm ảnh" takes the first photo for the saved keywords; pressed again it moves on to another one.
  const second = scenes.nth(1);
  await second.getByRole("button", { name: "Tìm ảnh" }).click();
  await expect(second.getByTestId("scene-preview")).toBeVisible();
  const before = await second.getByTestId("scene-preview").getAttribute("src");
  await second.getByRole("button", { name: "Tìm ảnh" }).click();
  await expect(second.getByTestId("scene-preview")).not.toHaveAttribute("src", before ?? "");

  // Without keywords the api's own message is shown, with a pointer to the keyword field.
  const third = scenes.nth(2);
  await third.getByLabel("Từ khóa tìm ảnh").fill("");
  await third.getByLabel("Từ khóa tìm ảnh").blur();
  await expect(third.getByText("Đã lưu")).toBeVisible();
  await third.getByRole("button", { name: "Tìm ảnh" }).click();
  await expect(third.getByTestId("image-error")).toHaveText("Hãy nhập từ khóa tìm ảnh trước");
  await expect(third.getByTestId("keywords-hint")).toBeVisible();
  // The grid then waits for a keyword to be typed instead of searching nothing.
  await third.getByRole("button", { name: "Chọn từ kho ảnh" }).click();
  picker = page.getByRole("dialog", { name: "Chọn từ kho ảnh" });
  await expect(picker.getByTestId("picker-hint")).toBeVisible();
  await expect(picker.getByTestId("stock-hit")).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(picker).toBeHidden();
  await third.getByLabel("Từ khóa tìm ảnh").fill("đậu phụ rán");
  await third.getByLabel("Từ khóa tìm ảnh").blur();
  await expect(third.getByText("Đã lưu")).toBeVisible();

  // Once every scene has a photo the render is no longer blocked.
  for (let index = 2; index < 5; index++) {
    await scenes.nth(index).getByRole("button", { name: "Tìm ảnh" }).click();
    await expect(scenes.nth(index).getByTestId("scene-preview")).toBeVisible();
  }
  await expect(page.getByTestId("scene-blocking")).toHaveCount(0);
  await expect(render).toBeEnabled();
  await page.reload();
  await expect(page.getByTestId("scene-preview")).toHaveCount(6);

  // On a phone the grid fits the screen: no sideways scroll, thumbnails still large enough to tell apart.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByTestId("scene").first().getByRole("button", { name: "Chọn từ kho ảnh" }).click();
  picker = page.getByRole("dialog", { name: "Chọn từ kho ảnh" });
  // The photo this scene already shows is hidden ("Ẩn ảnh đã dùng trong video này" is on by default).
  await expect(picker.getByTestId("stock-hit")).toHaveCount(2);
  for (const hit of await picker.getByTestId("stock-hit").all()) {
    await expect.poll(async () => (await hit.boundingBox())?.width).toBeGreaterThanOrEqual(140);
    const place = await hit.boundingBox();
    expect((place?.x ?? 0) + (place?.width ?? 0)).toBeLessThanOrEqual(390);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

// A 1×1 PNG, as Google Ảnh's thumbnails arrive: a data: address rather than a file.
const PNG_DATA_URL =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

test("photos from other sites: paste a photo or its link, drag one from another tab, open Google Ảnh", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("canxi cho người lớn tuổi");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await jobFinished(page);
  const scenes = page.getByTestId("scene");

  // "Tìm trên Google" opens Google Ảnh on the scene's first keyword, tall photos only.
  await page.context().route("https://www.google.com/**", (route) => route.fulfill({ body: "Google Ảnh" }));
  const opened = page.waitForEvent("popup");
  await scenes.nth(0).getByRole("button", { name: "Tìm trên Google" }).click();
  const google = new URL((await opened).url());
  expect(google.pathname).toBe("/search");
  expect(google.searchParams.get("q")).toBeTruthy();
  expect(google.searchParams.get("udm")).toBe("2");
  expect(google.searchParams.get("tbs")).toBe("iar:t");

  // "Dán ảnh/link" without clipboard permission opens a box; a copied thumbnail's data: address is uploaded.
  await scenes.nth(0).getByRole("button", { name: "Dán ảnh/link" }).click();
  let paste = page.getByRole("dialog", { name: /Dán ảnh cho/ });
  await paste.getByLabel("Link ảnh").fill(PNG_DATA_URL);
  const uploaded = page.waitForRequest((request) => request.method() === "POST" && /\/image$/.test(request.url()));
  await paste.getByRole("button", { name: "Lấy ảnh" }).click();
  await uploaded;
  await expect(scenes.nth(0).getByTestId("scene-preview")).toBeVisible();

  // A link is fetched by the api, which only reaches the public internet: this machine's address is refused.
  await scenes.nth(1).getByRole("button", { name: "Dán ảnh/link" }).click();
  paste = page.getByRole("dialog", { name: /Dán ảnh cho/ });
  await paste.getByLabel("Link ảnh").fill("http://127.0.0.1:9/anh.jpg");
  await paste.getByRole("button", { name: "Lấy ảnh" }).click();
  await expect(scenes.nth(1).getByTestId("image-error")).toContainText("địa chỉ nội bộ");

  // A photo dragged from another tab arrives as its <img>, not as a file.
  const transfer = await page.evaluateHandle((src) => {
    const data = new DataTransfer();
    data.setData("text/html", `<img src="${src}" alt="">`);
    return data;
  }, PNG_DATA_URL);
  await scenes.nth(2).getByTestId("scene-dropzone").dispatchEvent("drop", { dataTransfer: transfer });
  await expect(scenes.nth(2).getByTestId("scene-preview")).toBeVisible();
});

test("picker filters: keyword chips, photo shape, and photos already in the video", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("canxi cho người lớn tuổi");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await jobFinished(page);
  const scenes = page.getByTestId("scene");

  // The first scene takes the first result; the second scene's picker, on the same keyword, no longer offers it.
  await scenes.nth(0).getByRole("button", { name: "Chọn từ kho ảnh" }).click();
  let picker = page.getByRole("dialog", { name: "Chọn từ kho ảnh" });
  await expect(picker.getByTestId("stock-hit")).toHaveCount(3);
  const taken = await picker.getByTestId("stock-hit").first().locator("img").getAttribute("src");
  await picker.getByTestId("stock-hit").first().click();
  await expect(picker).toBeHidden();

  await scenes.nth(1).getByRole("button", { name: "Chọn từ kho ảnh" }).click();
  picker = page.getByRole("dialog", { name: "Chọn từ kho ảnh" });
  // The scene's own keywords are one tap away; the first scene's keyword finds the photo already taken.
  await expect(picker.getByTestId("keyword-chips")).toContainText("yogurt");
  await picker.getByLabel("Từ khóa tìm ảnh").fill("small fried fish");
  await picker.getByLabel("Từ khóa tìm ảnh").press("Enter");
  await expect(picker.getByTestId("stock-hit")).toHaveCount(2);
  await expect(picker.locator(`img[src="${taken}"]`)).toHaveCount(0);
  await picker.getByText("Ẩn ảnh đã dùng trong video này").click();
  await expect(picker.getByTestId("stock-hit")).toHaveCount(3);

  // Another shape searches again with it.
  const square = page.waitForRequest((request) => /\/stock\?.*orientation=square/.test(request.url()));
  await picker.getByLabel("Hướng ảnh").getByText("Vuông").click();
  await square;
  const chip = page.waitForRequest((request) => /\/stock\?q=yogurt&/.test(request.url()));
  await picker.getByTestId("keyword-chips").getByText("yogurt", { exact: true }).click();
  await chip;
  await expect(picker.getByLabel("Từ khóa tìm ảnh")).toHaveValue("yogurt");
});

test("photos from Pexels and Openverse: switch sources inside the picker", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "món ăn tốt cho xương");
  const scene = page.getByTestId("scene").first();
  await scene.getByRole("button", { name: "Chọn từ kho ảnh" }).click();
  const picker = page.getByRole("dialog", { name: "Chọn từ kho ảnh" });
  // Pixabay is the default source: its three fake photos show first.
  await expect(picker.getByTestId("stock-hit")).toHaveCount(3);
  await picker.getByText("Pexels", { exact: true }).click();
  await expect(picker.getByText(/ảnh từ Pexels cho/)).toBeVisible();
  // The page polls the video every 2.5 s; a poll must not send the picker back to Pixabay.
  const poll = (response: { url(): string; request(): { method(): string } }) =>
    /\/api\/videos\/\d+$/.test(response.url()) && response.request().method() === "GET";
  await page.waitForResponse(poll);
  await page.waitForResponse(poll);
  await expect(picker.getByText(/ảnh từ Pexels cho/)).toBeVisible();
  await expect(picker.getByRole("radio", { name: "Pexels" })).toBeChecked();
  await expect(picker.getByTestId("stock-hit")).toHaveCount(3);
  await picker.getByTestId("stock-hit").first().click();
  await expect(picker).toBeHidden();
  await expect(scene.getByTestId("scene-preview")).toBeVisible();

  // Reopen and take a photo from Openverse instead; the picker starts on Pixabay again.
  await scene.getByRole("button", { name: "Chọn từ kho ảnh" }).click();
  await picker.getByText("Openverse", { exact: true }).click();
  await expect(picker.getByText(/ảnh từ Openverse cho/)).toBeVisible();
  await expect(picker.getByTestId("stock-hit")).toHaveCount(3);
  await picker.getByTestId("stock-hit").nth(1).click();
  await expect(picker).toBeHidden();
  await expect(scene.getByTestId("scene-preview")).toBeVisible();

  // "Tìm ảnh" searches Pixabay until another source is picked from its arrow menu.
  const find = scene.getByRole("button", { name: "Tìm ảnh (Pixabay)" });
  await expect(find).toBeVisible();
  await scene.getByRole("button", { name: "Đổi nguồn ảnh" }).click();
  await page.getByRole("menuitem", { name: "Openverse" }).click();
  const fromOpenverse = page.waitForRequest(
    (request) => request.method() === "POST" && /\/find-image\?source=openverse$/.test(request.url()),
  );
  await scene.getByRole("button", { name: "Tìm ảnh (Openverse)" }).click();
  await fromOpenverse;
  await expect(scene.getByTestId("image-error")).toHaveCount(0);
  await expect(scene.getByTestId("scene-preview")).toBeVisible();
});

test("AI photos fill the scenes that have none, then the video can render", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("canxi cho xương khớp");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await jobFinished(page);

  // No scene has a photo yet: the AI button is offered and Render stays blocked.
  await expect(page.getByRole("button", { name: "Render" })).toBeDisabled();
  await page.getByRole("button", { name: "Tạo ảnh AI cho cảnh thiếu" }).click();
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 120_000 });

  await expect(page.getByTestId("title-scene").getByTestId("scene-preview")).toBeVisible({ timeout: 30_000 });
  const scenes = page.getByTestId("scene");
  for (let index = 0; index < (await scenes.count()); index++) {
    await expect(scenes.nth(index).getByTestId("scene-preview")).toBeVisible();
  }
  // Every scene has a photo now: the button is gone and Render is unblocked.
  await expect(page.getByRole("button", { name: "Tạo ảnh AI cho cảnh thiếu" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Render" })).toBeEnabled();
});

test("an AI photo for one scene, then a new one in its place", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("canxi cho xương khớp");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await jobFinished(page);
  const scenes = page.getByTestId("scene");

  // Only the chosen scene gets a photo; the others stay empty.
  await scenes.nth(1).getByRole("button", { name: "Tạo ảnh AI" }).click();
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 120_000 });
  const preview = scenes.nth(1).getByTestId("scene-preview");
  await expect(preview).toBeVisible({ timeout: 30_000 });
  await expect(scenes.nth(0).getByTestId("scene-preview")).toHaveCount(0);
  await expect(scenes.nth(2).getByTestId("scene-preview")).toHaveCount(0);

  // An AI photo can be made again, after a confirmation, and replaces the one shown.
  const first = await preview.getAttribute("src");
  await scenes.nth(1).getByRole("button", { name: "Tạo lại ảnh AI" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Đổi" }).click();
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 120_000 });
  await expect(preview).not.toHaveAttribute("src", first ?? "", { timeout: 30_000 });
});

test("AI image provider: the team default on Nguồn tư liệu, another one for a single press", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  await page.goto("/settings/sources");
  // The starting default depends on the server's .env (IMAGE_GEN_PROVIDER); choosing one here wins over it.
  const choice = page.getByTestId("ai-provider");
  await choice.getByLabel("Nguồn ảnh AI mặc định").getByText("Cloudflare (miễn phí)").click();
  await expect(choice.locator(".ant-segmented-item-selected")).toHaveText("Cloudflare (miễn phí)");
  await choice.getByLabel("Nguồn ảnh AI mặc định").getByText("Gemini (tốn phí)").click();
  await expect(choice.locator(".ant-segmented-item-selected")).toHaveText("Gemini (tốn phí)");
  // The shared style every AI prompt ends with: edited here, kept after a reload, back to the default on request.
  const style = choice.getByLabel("Phong cách ảnh AI");
  await expect(style).toHaveValue(/no text/);
  await style.fill("watercolor illustration, pastel colours");
  await choice.getByRole("button", { name: "Lưu phong cách" }).click();
  await page.reload();
  await expect(page.getByTestId("ai-provider").getByLabel("Phong cách ảnh AI")).toHaveValue(
    "watercolor illustration, pastel colours",
  );
  await page.getByTestId("ai-provider").getByRole("button", { name: "Dùng mặc định" }).click();
  await expect(page.getByTestId("ai-provider").getByLabel("Phong cách ảnh AI")).toHaveValue(/no text/);

  await page.goto("/videos");
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("canxi cho xương khớp");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await jobFinished(page);

  // The script writes an English AI prompt for the title scene too.
  await expect(page.getByTestId("title-scene").getByLabel("Prompt ảnh AI")).toHaveValue(/Calcium-rich/);

  // One scene with Cloudflare, picked from the arrow; then the rest with the team's default (Gemini).
  await page.getByTestId("scene").nth(0).getByRole("button", { name: "Chọn nguồn ảnh AI" }).click();
  await page.getByRole("menuitem", { name: /Tạo bằng Cloudflare/ }).click();
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 120_000 });
  await expect(page.getByTestId("scene").nth(0).getByTestId("scene-preview")).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Tạo ảnh AI cho cảnh thiếu" }).click();
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 120_000 });
  await expect(page.getByRole("button", { name: "Tạo ảnh AI cho cảnh thiếu" })).toHaveCount(0, { timeout: 30_000 });

  // The job log names the provider each image job used.
  await page.getByRole("menuitem", { name: "Job logs" }).click();
  await expect(page.getByRole("row", { name: /Tạo ảnh AI \(1 cảnh\).*Cloudflare/ })).toBeVisible();
  await expect(page.getByRole("row", { name: /Tạo ảnh AI(?! \(1 cảnh\)).*Gemini/ })).toBeVisible();
});

test("Tự tìm ảnh: after the script every scene gets a stock photo marked to check", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  // Off for the other E2E tests (api/scripts/e2e_reset.py); on by default for a real team.
  await page.goto("/settings/sources");
  const auto = page.getByRole("switch", { name: "Tự tìm ảnh sau khi viết kịch bản" });
  await expect(auto).not.toBeChecked();
  await auto.click();
  await expect(auto).toBeChecked();

  await page.goto("/videos");
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("canxi cho xương khớp");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page.getByTestId("scene")).toHaveCount(5, { timeout: 90_000 });

  // The photo search runs as its own job after the script; every scene, the title included, gets a photo.
  await expect(page.getByTestId("image-auto")).toHaveCount(6, { timeout: 120_000 });
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 60_000 });
  await expect(page.getByTestId("scene-preview")).toHaveCount(6);
  await expect(page.getByRole("button", { name: "Render" })).toBeEnabled();

  // A member keeps a pick, or replaces it: either way its mark goes.
  await page.getByTestId("scene").nth(0).getByRole("button", { name: "Giữ ảnh này" }).click();
  await expect(page.getByTestId("image-auto")).toHaveCount(5);
  await page.getByTestId("scene").nth(1).getByRole("button", { name: "Tìm ảnh" }).click();
  await expect(page.getByTestId("image-auto")).toHaveCount(4);

  await page.getByRole("menuitem", { name: "Job logs" }).click();
  await expect(page.getByRole("row", { name: /Tự tìm ảnh/ })).toBeVisible();
});

test("add and remove music", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau củ tốt cho tim");

  await page.getByLabel("Tải nhạc MP3 lên").setInputFiles(makeMp3());
  await expect(page.getByTestId("music-name")).toHaveText(/e2e-tone-\d+\.mp3/);
  await expect(page.getByText("Âm lượng: 25%")).toBeVisible();
  await page.getByLabel("Tải nhạc MP3 lên").setInputFiles({
    name: "gia.mp3",
    mimeType: "audio/mpeg",
    buffer: Buffer.from("RIFF0000WAVEfmt fake audio"),
  });
  await expect(page.getByText("File nhạc phải là MP3 thật", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Gỡ nhạc" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Gỡ nhạc" }).click();
  await expect(page.getByRole("button", { name: "Tải nhạc MP3 lên" })).toBeVisible();
});

test("add a track to the music library, then choose it for a video", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await page.goto("/music");
  await page.getByLabel("Chọn file MP3 cho thư viện").setInputFiles(makeMp3());
  const add = page.getByRole("dialog", { name: "Thêm vào thư viện nhạc" });
  await add.getByLabel("Tên bài").fill("Piano xương khớp");
  await chooseOption(page, add.getByLabel("Chủ đề"), "xương khớp");
  // A multiple select stays open after a pick and would cover the Mood field: click away to close it.
  await add.getByText("File:").click();
  await chooseOption(page, add.getByLabel("Mood"), "piano");
  await add.getByRole("button", { name: "Thêm" }).click();
  await expect(add).toBeHidden();
  const rows = page.locator(".ant-table-tbody .ant-table-row");
  await expect(rows.filter({ hasText: "Piano xương khớp" })).toHaveCount(1);

  await newVideoWithScript(page, "xương khớp sau 50 tuổi");
  await page.getByRole("button", { name: "Chọn từ thư viện" }).click();
  const picker = page.getByRole("dialog", { name: "Chọn nhạc từ thư viện" });
  // The unfiltered list arrives first, so the empty result below really comes from the filter.
  await expect(picker.getByTestId("library-track")).toHaveCount(1);
  await chooseOption(page, picker.getByLabel("Lọc theo mood"), "vui tươi");
  await expect(picker.getByTestId("library-track")).toHaveCount(0);
  await chooseOption(page, picker.getByLabel("Lọc theo mood"), "piano");
  await expect(picker.getByTestId("library-track")).toHaveCount(1);
  await picker.getByRole("button", { name: "Dùng bài này" }).click();
  await expect(picker).toBeHidden();
  await expect(page.getByTestId("music-name")).toHaveText("Piano xương khớp");
  await expect(page.getByText("Âm lượng: 25%")).toBeVisible();

  // An upload can go to the library too, then plays on the video.
  await page.getByRole("checkbox", { name: "Lưu file tải lên vào thư viện nhạc" }).check();
  await page.getByLabel("Tải nhạc MP3 lên").setInputFiles(makeMp3());
  const save = page.getByRole("dialog", { name: "Thêm vào thư viện nhạc" });
  await save.getByLabel("Tên bài").fill("Tim nhẹ nhàng");
  await chooseOption(page, save.getByLabel("Chủ đề"), "tim mạch");
  await save.getByText("File:").click();
  await chooseOption(page, save.getByLabel("Mood"), "nhẹ nhàng");
  await save.getByRole("button", { name: "Thêm" }).click();
  await expect(save).toBeHidden();
  await expect(page.getByTestId("music-name")).toHaveText("Tim nhẹ nhàng");
  await page.goto("/music");
  await expect(rows.filter({ hasText: "Tim nhẹ nhàng" })).toHaveCount(1);

  // Edit and delete in the library; the video keeps its own copy.
  await rows.filter({ hasText: "Tim nhẹ nhàng" }).getByRole("button", { name: "Sửa" }).click();
  const edit = page.getByRole("dialog", { name: "Sửa bài nhạc" });
  await expect(edit.getByLabel("Tên bài")).toHaveValue("Tim nhẹ nhàng");
  await edit.getByLabel("Tên bài").fill("Tim buổi sáng");
  await edit.getByRole("button", { name: "Lưu" }).click();
  await expect(edit).toBeHidden();
  await expect(rows.filter({ hasText: "Tim buổi sáng" })).toHaveCount(1);
  await rows.filter({ hasText: "Tim buổi sáng" }).getByRole("button", { name: "Xoá" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Xoá" }).click();
  await expect(rows.filter({ hasText: "Tim buổi sáng" })).toHaveCount(0);
  await page.goBack();
  await expect(page.getByTestId("music-name")).toHaveText("Tim nhẹ nhàng");
});

test("clone a video with a change request, then see every job in the job log", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "xương khớp sau 50 tuổi");
  await page.getByLabel("Tải nhạc MP3 lên").setInputFiles(makeMp3());
  await expect(page.getByTestId("music-name")).toBeVisible();
  const sourceUrl = page.url();

  await page.getByRole("button", { name: "Nhân bản" }).click();
  const dialog = page.getByRole("dialog", { name: "Nhân bản video" });
  await expect(dialog.getByRole("button", { name: "Tạo bản nhân bản" })).toBeDisabled();
  await dialog.getByLabel("Yêu cầu đổi").fill("đổi sang mốc 45 tuổi, tim mạch");
  await dialog.getByRole("button", { name: "Tạo bản nhân bản" }).click();

  await expect(page).not.toHaveURL(sourceUrl);
  await expect(page.getByTestId("clone-of")).toContainText("đổi sang mốc 45 tuổi, tim mạch");
  await jobFinished(page);
  await expect(page.getByTestId("music-name")).toBeVisible();

  await page.getByRole("menuitem", { name: "Job logs" }).click();
  await expect(page).toHaveURL(/\/jobs$/);
  const rows = page.locator(".ant-table-tbody .ant-table-row");
  await expect(rows.filter({ hasText: "Nhân bản" })).toHaveCount(1);
  await expect(rows.filter({ hasText: "Viết kịch bản" })).toHaveCount(1);
  await expect(rows.first()).toContainText("Xong");
  await expect(rows.first()).toContainText(SEED.name);
  await rows.filter({ hasText: "Viết kịch bản" }).click();
  await expect(page).toHaveURL(sourceUrl);
});

function makeClip(): string {
  const file = path.join(os.tmpdir(), `e2e-clip-${process.pid}.mp4`);
  execFileSync("ffmpeg", [
    "-v",
    "error",
    "-y",
    "-f",
    "lavfi",
    "-i",
    "testsrc2=size=1280x720:rate=25:duration=3",
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    file,
  ]);
  return file;
}

test("a title clip with a start time renders, and removing it asks for a photo again", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau dền nấu theo cách này");

  const title = page.getByTestId("title-scene");
  const before = await title.getByTestId("scene-preview").getAttribute("src");
  // The title has a photo: the clip replaces it only after a confirmation.
  const media = title.getByLabel("Tải ảnh/video lên cho cảnh tiêu đề");
  await media.setInputFiles(makeClip());
  await page
    .getByRole("dialog")
    .filter({ hasText: "Video sẽ thay ảnh của cảnh này?" })
    .getByRole("button", { name: "Đổi" })
    .click();
  await expect(title.getByTestId("scene-video")).toBeVisible();
  await expect(title.getByTestId("scene-preview")).not.toHaveAttribute("src", before ?? "");
  // 3 s of clip minus the 0.2 s the title plays into its crossfade.
  await expect(title.getByLabel("Số giây")).toHaveValue("2.8");

  // Switching back to a photo asks first; cancelling keeps the clip.
  await media.setInputFiles(path.join(os.tmpdir(), `e2e-photo-${process.pid}.jpg`));
  const confirm = page.getByRole("dialog").filter({ hasText: "Ảnh sẽ thay video của cảnh này?" });
  await confirm.getByRole("button", { name: "Huỷ" }).click();
  await expect(title.getByTestId("scene-video")).toBeVisible();

  // "Cắt video": the two handles pick the part the scene plays; too short a part cannot be applied.
  await title.getByRole("button", { name: "Cắt video" }).click();
  const trim = page.getByRole("dialog", { name: "Cắt video cảnh tiêu đề" });
  const from = trim.getByRole("slider").first();
  await from.focus();
  for (let step = 0; step < 25; step++) {
    await from.press("ArrowRight");
  }
  await expect(trim.getByTestId("trim-problem")).toBeVisible();
  await expect(trim.getByRole("button", { name: "Áp dụng" })).toBeDisabled();
  for (let step = 0; step < 20; step++) {
    await from.press("ArrowLeft");
  }
  // 3 s of clip from 0.5 s, less the title's 0.2 s crossfade.
  await expect(trim.getByTestId("trim-range")).toContainText("cảnh dài 2,3 giây");
  await trim.getByRole("button", { name: "Áp dụng" }).click();
  await expect(trim).toHaveCount(0);
  await expect(title.getByLabel("Số giây")).toHaveValue("2.3");

  const start = title.getByLabel("Bắt đầu từ giây");
  await expect(start).toHaveValue("0.5");
  await start.fill("1,5");
  await start.blur();
  await expect(title.getByText("Video ngắn hơn cảnh, khung cuối sẽ đứng yên")).toBeVisible();

  await page.getByRole("button", { name: "Render" }).click();
  await expect(page.getByTestId("video-status")).toHaveText("Xong", { timeout: 120_000 });

  await title.getByRole("button", { name: "Xoá video" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Xoá" }).click();
  await expect(title.getByTestId("scene-video")).toHaveCount(0);
  await expect(title.getByTestId("scene-no-preview")).toHaveText("Chưa có ảnh");
  await expect(page.getByText("MP4 chưa cập nhật theo bản sửa")).toBeVisible();
});

test("AI model settings: set up an OpenAI-compatible provider, check it, and write a script with it", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Cấu hình" }).click();
  // A tab clicked before /settings redirects to its first tab loses to that redirect.
  await expect(page).toHaveURL(/\/settings\/defaults$/);
  await page.getByRole("tab", { name: "Mô hình AI" }).click();
  await expect(page).toHaveURL(/\/settings\/ai$/);
  // With nothing set, the team writes with Claude from the server's environment.
  const claude = page.getByTestId("provider-anthropic");
  await expect(claude.getByTestId("key-status")).toHaveText("Đang dùng key trong file .env của máy chủ");

  await page.getByRole("button", { name: /Tùy chỉnh \(chuẩn OpenAI\)/ }).click();
  const custom = page.getByTestId("provider-custom");
  await custom.getByLabel("API key Tùy chỉnh (chuẩn OpenAI)").fill("fake-openai-key");
  await custom.getByRole("button", { name: "Lưu key" }).click();
  await expect(custom.getByTestId("key-status")).toHaveText("Đã lưu, kết thúc bằng …-key");
  await custom.getByLabel("Base URL Tùy chỉnh (chuẩn OpenAI)").fill("http://127.0.0.1:8199/openai/v1");
  await custom.getByLabel("Model Tùy chỉnh (chuẩn OpenAI)").fill("fake-gpt-mini");
  await custom.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(page.getByText("Đã lưu Tùy chỉnh (chuẩn OpenAI)")).toBeVisible();
  await custom.getByRole("button", { name: "Kiểm tra kết nối" }).click();
  await expect(page.getByText("Kết nối được Tùy chỉnh (chuẩn OpenAI) (2 model)")).toBeVisible();
  await custom.getByRole("button", { name: "Dùng để viết kịch bản" }).click();
  await expect(page.getByText("Từ giờ kịch bản được viết bằng Tùy chỉnh (chuẩn OpenAI)")).toBeVisible();
  await expect(page.getByLabel("Nhà cung cấp đang dùng").locator("..")).toContainText(
    "Tùy chỉnh (chuẩn OpenAI) · fake-gpt-mini",
  );

  await page.getByRole("menuitem", { name: "Video" }).click();
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await expect(dialog.getByTestId("llm-line")).toContainText("Viết bằng: Tùy chỉnh (chuẩn OpenAI) · fake-gpt-mini");
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("xương khớp sau 50 tuổi");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await jobFinished(page);
  await expect(page.getByTestId("script-by")).toHaveText("Kịch bản viết bởi Tùy chỉnh (chuẩn OpenAI) · fake-gpt-mini");

  await page.getByRole("menuitem", { name: "Job logs" }).click();
  await expect(page.locator(".ant-table-tbody .ant-table-row").first()).toContainText(
    "Tùy chỉnh (chuẩn OpenAI) · fake-gpt-mini",
  );
});

test("video settings: team defaults reach a new video, which then changes its own", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Cấu hình" }).click();
  await page.getByRole("tab", { name: "Thiết lập mặc định" }).click();
  await expect(page).toHaveURL(/\/settings\/defaults$/);
  await page.getByLabel("Chuyển cảnh").getByText("Cắt thẳng").click();
  await expect(page.getByText("Đã lưu mặc định")).toBeVisible();
  await page.getByLabel("Tốc độ đọc").getByText("Nhanh").click();
  await expect(page.getByTestId("audio-settings")).toContainText("Adam (mặc định)");

  await page.getByRole("menuitem", { name: "Video" }).click();
  await newVideoWithScript(page, "xương khớp sau 50 tuổi");
  await page.getByRole("tab", { name: "Thiết lập" }).click();
  const motion = page.getByTestId("motion-settings");
  await expect(motion.getByLabel("Chuyển cảnh").locator(".ant-segmented-item-selected")).toHaveText("Cắt thẳng");
  await expect(page.getByLabel("Tốc độ đọc").locator(".ant-segmented-item-selected")).toHaveText("Nhanh");

  // The old preset boxes are gone: a member adds a team style, which the video picks at once.
  const preview = page.getByTestId("title-scene").getByTestId("scene-preview");
  const before = await preview.getAttribute("src");
  await expect(page.getByRole("radio", { name: "Kiểu Vàng" })).toHaveCount(0);
  await page.getByRole("button", { name: "Thêm kiểu" }).click();
  const editor = page.getByRole("dialog", { name: "Thêm kiểu hộp chữ" });
  await editor.getByLabel("Tên kiểu").fill("Tối");
  await editor.getByRole("radio", { name: "Kiểu nền Đen" }).click();
  await editor.getByLabel("Độ trong của kiểu").getByText("Hơi trong").click();
  await editor.getByRole("radio", { name: "Kiểu chữ Trắng" }).click();
  await editor.getByRole("button", { name: "Thêm kiểu" }).click();
  await expect(page.getByText("Đã thêm kiểu “Tối”")).toBeVisible();
  await expect(page.getByRole("radio", { name: "Kiểu Tối" })).toHaveAttribute("aria-checked", "true");
  await expect(preview).not.toHaveAttribute("src", before ?? "");
  // Black letters would vanish into the dark box: allowed, with a warning; yellow ones redraw the previews again.
  await page.getByRole("radio", { name: "Màu Đen" }).click();
  await expect(page.getByTestId("color-warning")).toContainText("Chữ khó đọc trên nền hộp này.");
  // The video's own colours no longer match the team style, which stays as it was.
  await expect(page.getByRole("radio", { name: "Kiểu Tối" })).toHaveAttribute("aria-checked", "false");
  const dark = await preview.getAttribute("src");
  await page.getByRole("radio", { name: "Màu Vàng" }).click();
  await expect(page.getByRole("radio", { name: "Màu Vàng" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("color-warning")).toHaveCount(0);
  await expect(preview).not.toHaveAttribute("src", dark ?? "");
  // A box colour and an opacity of its own redraw them too.
  const yellow = await preview.getAttribute("src");
  await page.getByRole("radio", { name: "Nền Xanh dương" }).click();
  await expect(page.getByRole("radio", { name: "Nền Xanh dương" })).toHaveAttribute("aria-checked", "true");
  await expect(preview).not.toHaveAttribute("src", yellow ?? "");
  const blue = await preview.getAttribute("src");
  await page.getByLabel("Độ trong của hộp").getByText("Đặc").click();
  await expect(preview).not.toHaveAttribute("src", blue ?? "");
  // No background outlines the letters, in the box colour.
  const solid = await preview.getAttribute("src");
  await page.getByLabel("Độ trong của hộp").getByText("Không nền").click();
  await expect(page.getByRole("radio", { name: "Viền Xanh dương" })).toHaveAttribute("aria-checked", "true");
  await expect(preview).not.toHaveAttribute("src", solid ?? "");
  // Picking the style again brings its colours back; deleting it leaves the video's copy alone.
  await page.getByRole("radio", { name: "Kiểu Tối" }).click();
  await expect(page.getByRole("radio", { name: "Kiểu Tối" })).toHaveAttribute("aria-checked", "true");
  const styled = await preview.getAttribute("src");
  await page.getByRole("button", { name: "Xoá kiểu" }).click();
  await page.getByRole("button", { name: "Xoá", exact: true }).click();
  await expect(page.getByRole("radio", { name: "Kiểu Tối" })).toHaveCount(0);
  await expect(preview).toHaveAttribute("src", styled ?? "");
  // No box keeps the text colour and brings its own outline.
  await page.getByRole("radio", { name: "Kiểu Không hộp" }).click();
  await expect(page.getByRole("radio", { name: "Kiểu Không hộp" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("radio", { name: "Màu Trắng" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("radio", { name: "Viền Theo kiểu" })).toHaveAttribute("aria-checked", "true");
  // The title takes a look of its own, with the same controls; the scenes keep theirs.
  const titlePreview = page.getByTestId("title-scene").getByTestId("scene-preview");
  const scenePreview = page.getByTestId("scene").first().getByTestId("scene-preview");
  const outlinedTitle = await titlePreview.getAttribute("src");
  const outlinedScene = await scenePreview.getAttribute("src");
  await page.getByLabel("Chỉnh chữ cho").getByText("Tiêu đề").click();
  const follows = page.getByRole("checkbox", { name: "Tiêu đề giống các cảnh" });
  await expect(follows).toBeChecked();
  await expect(page.getByLabel("Phụ đề theo giọng đọc")).toHaveCount(0);
  // The box follows what the api saved, so it is clicked and then awaited.
  await follows.click();
  await expect(follows).not.toBeChecked();
  // It starts from the scenes' look, so nothing changes until a choice of its own.
  await expect(page.getByRole("radio", { name: "Kiểu Không hộp" })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("radio", { name: "Màu Đỏ" }).click();
  await expect(page.getByRole("radio", { name: "Màu Đỏ" })).toHaveAttribute("aria-checked", "true");
  await expect(titlePreview).not.toHaveAttribute("src", outlinedTitle ?? "");
  await expect(scenePreview).toHaveAttribute("src", outlinedScene ?? "");
  // Following the scenes again drops the title's own look.
  await follows.click();
  await expect(follows).toBeChecked();
  await expect(titlePreview).toHaveAttribute("src", outlinedTitle ?? "");
  await page.getByLabel("Chỉnh chữ cho").getByText("Các cảnh").click();

  // Captions need narration.
  await page.getByRole("switch", { name: "Đọc lời từng cảnh" }).click();
  await expect(page.getByLabel("Phụ đề theo giọng đọc").locator("input").first()).toBeDisabled();
  await expect(page.getByText("Cần bật giọng đọc.")).toBeVisible();
});

test("stock clips: pick a vertical clip for a scene, and a source turned off leaves the picker", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("canxi cho người lớn tuổi");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await jobFinished(page);

  const scene = page.getByTestId("scene").first();
  await scene.getByRole("button", { name: "Chọn từ kho ảnh/video" }).click();
  const picker = page.getByRole("dialog", { name: "Chọn từ kho ảnh/video" });
  await picker.getByText("Video", { exact: true }).click();
  // Pixabay offers clips too, Openverse does not.
  await expect(picker.getByLabel("Nguồn video")).toContainText("Pexels");
  await expect(picker.getByLabel("Nguồn video")).not.toContainText("Openverse");
  await expect(picker.getByTestId("clip-hit")).toHaveCount(3);
  await picker.getByRole("button", { name: "Chọn video 2" }).click();
  await expect(picker).toBeHidden({ timeout: 30_000 });
  await expect(scene.getByTestId("scene-video")).toBeVisible();
  const videoUrl = page.url();

  await page.getByRole("menuitem", { name: "Cấu hình" }).click();
  await expect(page).toHaveURL(/\/settings\/defaults$/);
  await page.getByRole("tab", { name: "Nguồn tư liệu" }).click();
  await expect(page).toHaveURL(/\/settings\/sources$/);
  await page.getByRole("switch", { name: "Bật Pexels" }).click();
  await expect(page.getByRole("switch", { name: "Bật Pexels" })).not.toBeChecked();
  // A key pasted here is stored encrypted and only its last characters come back.
  const pixabayKey = page.getByTestId("key-pixabay");
  await expect(pixabayKey.getByTestId("key-status")).toHaveText("Đang dùng key trong file .env của máy chủ");
  await pixabayKey.getByRole("button", { name: "Dán key mới" }).click();
  await pixabayKey.getByLabel("API key Pixabay").fill("fake-pixabay-key");
  await pixabayKey.getByRole("button", { name: "Lưu key" }).click();
  await expect(pixabayKey.getByTestId("key-status")).toHaveText("Đã lưu, kết thúc bằng …-key");
  // The ElevenLabs key for narration is pasted on the same page.
  const voiceKey = page.getByTestId("key-elevenlabs");
  await voiceKey.getByRole("button", { name: "Dán key mới" }).click();
  await voiceKey.getByLabel("API key ElevenLabs").fill("fake-elevenlabs-key");
  await voiceKey.getByRole("button", { name: "Lưu key" }).click();
  await expect(voiceKey.getByTestId("key-status")).toHaveText("Đã lưu, kết thúc bằng …-key");
  await expect(page.getByTestId("source-elevenlabs")).toContainText("Sẵn sàng");
  await page.goto(videoUrl);
  await page.getByTestId("scene").nth(1).getByRole("button", { name: "Chọn từ kho ảnh/video" }).click();
  await expect(picker.getByLabel("Nguồn ảnh")).not.toContainText("Pexels");
});

test("text settings from an api without the colour options still open, on Theo kiểu", async ({ page }) => {
  // An api older than the page (e.g. not restarted after an update) leaves the new colours out.
  await page.route("**/api/settings/video-defaults", async (route) => {
    const response = await route.fetch();
    const older = await response.json();
    delete older.box_color;
    delete older.accent_color;
    await route.fulfill({ response, json: older });
  });
  await loginAsSeed(page);
  await page.goto("/settings/defaults");
  const text = page.getByTestId("text-settings");
  await expect(text.getByRole("radio", { name: "Nền Theo kiểu" })).toHaveAttribute("aria-checked", "true");
  await expect(text.getByRole("radio", { name: "Đánh dấu Theo kiểu" })).toHaveAttribute("aria-checked", "true");
});

/** A dialog's box once its zoom-in has finished, so what is measured or dragged is where it stays. */
async function settledBox(page: Page, locator: ReturnType<Page["locator"]>) {
  await expect(page.locator('.ant-modal[class*="zoom"]')).toHaveCount(0);
  return locator.boundingBox();
}

test("drag a scene's text box inside the safe zone, for that scene or every scene, and move the title", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "xương khớp sau 50 tuổi");
  const first = page.getByTestId("scene").first();
  const second = page.getByTestId("scene").nth(1);
  const firstPreview = first.getByTestId("scene-preview");
  const secondPreview = second.getByTestId("scene-preview");
  const firstBefore = await firstPreview.getAttribute("src");
  const secondBefore = await secondPreview.getAttribute("src");

  // Dragged far up, the box stops at the top of the safe zone (y 220), clear of the platform's top bar.
  await first.getByRole("button", { name: "Vị trí chữ" }).click();
  const dialog = page.getByRole("dialog", { name: "Vị trí chữ của cảnh" });
  const box = dialog.getByTestId("position-box");
  await expect(box).toBeVisible();
  await expect(box).toHaveAttribute("aria-valuetext", /^x 540, /);
  const start = await settledBox(page, box);
  const grab = [(start?.x ?? 0) + (start?.width ?? 0) / 2, (start?.y ?? 0) + (start?.height ?? 0) / 2];
  await page.mouse.move(grab[0], grab[1]);
  await page.mouse.down();
  await page.mouse.move(grab[0], grab[1] - 260, { steps: 8 });
  await page.mouse.up();
  const frame = await dialog.getByTestId("position-frame").boundingBox();
  const moved = await box.boundingBox();
  expect(Math.round((moved?.y ?? 0) - (frame?.y ?? 0))).toBe(55); // 220 frame pixels at a quarter size
  await dialog.getByRole("button", { name: "Lưu cho cảnh này" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(firstPreview).not.toHaveAttribute("src", firstBefore ?? "");
  await expect(secondPreview).toHaveAttribute("src", secondBefore ?? "");
  await expect(first.getByRole("button", { name: "Vị trí chữ (riêng)" })).toBeVisible();

  // The arrow keys move it too; "Lưu cho mọi cảnh" moves the scenes without a place of their own.
  await second.getByRole("button", { name: "Vị trí chữ" }).click();
  const secondBox = page.getByRole("dialog", { name: "Vị trí chữ của cảnh" }).getByTestId("position-box");
  await expect(secondBox).toBeVisible();
  await secondBox.focus();
  for (let step = 0; step < 30; step += 1) {
    await page.keyboard.press("ArrowUp");
  }
  await page.getByRole("button", { name: "Lưu cho mọi cảnh" }).click();
  await expect(secondPreview).not.toHaveAttribute("src", secondBefore ?? "");
  const firstOwn = await firstPreview.getAttribute("src");
  await expect(first.getByRole("button", { name: "Vị trí chữ (riêng)" })).toBeVisible();
  expect(await firstPreview.getAttribute("src")).toBe(firstOwn);

  // Giving the scene's own place back makes it follow the video's.
  await first.getByRole("button", { name: "Vị trí chữ (riêng)" }).click();
  await page.getByRole("button", { name: "Bỏ vị trí riêng của cảnh này" }).click();
  await expect(first.getByRole("button", { name: "Vị trí chữ (riêng)" })).toHaveCount(0);

  // The title moves only up and down.
  const title = page.getByTestId("title-scene");
  const titleBefore = await title.getByTestId("scene-preview").getAttribute("src");
  await title.getByRole("button", { name: "Vị trí chữ" }).click();
  const titleBox = page.getByRole("dialog", { name: "Vị trí chữ cảnh tiêu đề" }).getByTestId("position-box");
  await expect(titleBox).toBeVisible();
  // Placed once its image has loaded: the title sits in the middle of the frame (x 539 or 540, as its width
  // is odd or even). Its place is read from the box's value, not from the screen.
  await expect(titleBox).toHaveAttribute("aria-valuetext", /^x 5(39|40), y 9\d\d$/);
  const [centredX, centredY] = ((await titleBox.getAttribute("aria-valuetext")) ?? "").match(/\d+/g)!.map(Number);
  await titleBox.focus();
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowDown");
  // Left does nothing, down moves it one step (10 frame pixels).
  await expect(titleBox).toHaveAttribute("aria-valuetext", `x ${centredX}, y ${centredY + 10}`);
  await page.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(title.getByTestId("scene-preview")).not.toHaveAttribute("src", titleBefore ?? "");
});

test("each member sees who else has the video open, and whether they are editing it", async ({ page, browser }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await addUser(page, "binh@doi.vn", "Trần Thị Bình", "tam-thoi-123");
  await page.goto("/videos");
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("xương khớp sau 50 tuổi");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await jobFinished(page);
  // A draft opens in "Chỉnh sửa"; nobody else is here yet.
  await expect(page.getByRole("button", { name: "Xong" })).toBeVisible();
  await expect(page.getByTestId("presence")).toHaveCount(0);

  const binh = await (await browser.newContext({ baseURL: "http://localhost:3100", locale: "vi-VN" })).newPage();
  await login(binh, "binh@doi.vn", "tam-thoi-123");
  await binh.getByLabel("Mật khẩu mới", { exact: true }).fill("binh-moi-1234");
  await binh.getByLabel("Nhập lại mật khẩu mới").fill("binh-moi-1234");
  await binh.getByRole("button", { name: "Lưu mật khẩu mới" }).click();
  await expect(binh).toHaveURL(/\/videos$/);
  await binh.goto(new URL(page.url()).pathname);
  await binh.getByRole("button", { name: "Xong" }).click();

  // Each sees the other within one report (10 s); An is editing, Bình only looking.
  const later = { timeout: 15_000 };
  await expect(binh.getByLabel(`${SEED.name} đang chỉnh sửa`)).toBeVisible(later);
  await expect(page.getByLabel("Trần Thị Bình đang xem")).toBeVisible(later);

  // Bình starts editing too: told that An is already editing, but not stopped.
  await binh.getByRole("button", { name: "Chỉnh sửa" }).click();
  await expect(binh.getByText("An đang chỉnh sửa video này.", { exact: false })).toBeVisible();
  await expect(binh.getByRole("button", { name: "Xong" })).toBeVisible();
  await expect(page.getByLabel("Trần Thị Bình đang chỉnh sửa")).toBeVisible(later);

  // Closing the tab leaves at once rather than after the 30 s time-out.
  await binh.close();
  await expect(page.getByTestId("presence")).toHaveCount(0, later);
});
