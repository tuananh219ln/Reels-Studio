import { execFileSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { SEED, chooseOption, connectFacebook, loginAsSeed, resetDatabase } from "./helpers";

// The api, a real worker with FFmpeg, and fake Claude/Pixabay (api/scripts/fake_services.py) all run.
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
  await expect(page.getByRole("button", { name: "Render" })).toBeDisabled();
  await uploadPhotos(page);
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

  // Members bring their own photos: the Pixabay search is not offered.
  await expect(first.getByTestId("scene-preview")).toBeVisible();
  await expect(first.getByRole("button", { name: "Tìm lại ảnh" })).toHaveCount(0);
  await expect(first.getByRole("button", { name: "Chọn từ Pixabay" })).toHaveCount(0);
  await expect(first.getByLabel("Từ khóa tìm ảnh")).toHaveCount(0);

  await page.reload();
  await expect(page.getByTestId("scene").first().getByLabel("Chữ trên màn hình")).toHaveValue(
    "Cá nhỏ chiên\nGiàu *canxi*",
  );

  await page.getByRole("button", { name: "Render" }).click();
  await expect(page.getByTestId("video-status")).toHaveText("Xong", { timeout: 120_000 });
  // 3 s title + 5 scenes of 1 s, each lengthened to fit its fake narration of 4 words (0.2 + 1.2 + 0.4 s).
  await expect(page.getByTestId("render-time")).toContainText("Dài 12.5 giây");
  await expect(first.getByTestId("voice-player")).toBeVisible();

  // Seeking needs Range answers (206) through the web app's /api proxy.
  const src = await page.getByTestId("mp4-player").getAttribute("src");
  const range = await page.request.get(src ?? "", { headers: { Range: "bytes=100-199" } });
  expect(range.status()).toBe(206);
  expect((await range.body()).length).toBe(100);
  const download = await page.request.get((await page.getByRole("link", { name: "Tải MP4" }).getAttribute("href")) ?? "");
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

test("knowledge topics: each opens from its line, keeps its own texts, and an empty one cannot make a video", async ({ page }) => {
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

  await page.getByRole("menuitem", { name: "Lịch đăng bài" }).click();
  await expect(page).toHaveURL(/\/calendar$/);
  await expect(page.getByRole("columnheader", { name: "T2" })).toBeVisible();
  await page.locator(".ant-picker-cell-in-view a[href^='/videos/']").click();
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

/** Gives the title and every content scene a photo, as a member does after the script is written. */
async function uploadPhotos(page: Page) {
  const file = path.join(os.tmpdir(), `e2e-photo-${process.pid}.jpg`);
  execFileSync("ffmpeg", ["-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1080x1280:rate=1",
    "-frames:v", "1", file]);
  await page.getByLabel("Tải ảnh lên cho cảnh tiêu đề").setInputFiles(file);
  await expect(page.getByTestId("title-scene").getByTestId("scene-preview")).toBeVisible();
  const scenes = page.getByTestId("scene");
  for (let index = 0; index < (await scenes.count()); index++) {
    await scenes.nth(index).getByLabel("Tải ảnh lên cho cảnh", { exact: true }).setInputFiles(file);
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
  execFileSync("ffmpeg", ["-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-ac", "2",
    "-c:a", "libmp3lame", "-b:a", "96k", file]);
  return file;
}

test("add and remove music", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau củ tốt cho tim");

  await page.getByLabel("Tải nhạc MP3 lên").setInputFiles(makeMp3());
  await expect(page.getByTestId("music-name")).toHaveText(/e2e-tone-\d+\.mp3/);
  await expect(page.getByText("Âm lượng: 25%")).toBeVisible();
  await page.getByLabel("Tải nhạc MP3 lên").setInputFiles({
    name: "gia.mp3", mimeType: "audio/mpeg", buffer: Buffer.from("RIFF0000WAVEfmt fake audio"),
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
  execFileSync("ffmpeg", ["-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=3",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", file]);
  return file;
}

test("a title clip with a start time renders, and removing it asks for a photo again", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau dền nấu theo cách này");

  const title = page.getByTestId("title-scene");
  const before = await title.getByTestId("scene-preview").getAttribute("src");
  // The title has a photo: the clip replaces it only after a confirmation, which then opens the file chooser.
  await title.getByRole("button", { name: "Tải video lên" }).click();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("tooltip").filter({ hasText: "Video sẽ thay ảnh của cảnh này?" })
    .getByRole("button", { name: "Đổi" }).click();
  await (await chooser).setFiles(makeClip());
  await expect(title.getByTestId("scene-video")).toBeVisible();
  await expect(title.getByTestId("scene-preview")).not.toHaveAttribute("src", before ?? "");
  // 3 s of clip minus the 0.2 s the title plays into its crossfade.
  await expect(title.getByLabel("Số giây")).toHaveValue("2.8");

  // Switching back to a photo asks first; cancelling keeps the clip.
  await title.getByRole("button", { name: "Tải ảnh lên" }).click();
  const confirm = page.getByRole("tooltip").filter({ hasText: "Ảnh sẽ thay video của cảnh này?" });
  await confirm.getByRole("button", { name: "Huỷ" }).click();
  await expect(title.getByTestId("scene-video")).toBeVisible();

  const start = title.getByLabel("Bắt đầu từ giây");
  await expect(start).toHaveValue("0");
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
