import { execFileSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { chooseOption, loginAsSeed, resetDatabase } from "./helpers";

// "Từ video mẫu": the real worker downloads nothing (the sample is uploaded), takes stills with FFmpeg, and reaches
// ElevenLabs Speech-to-Text and the LLM only through the fake services (api/scripts/fake_services.py).
test.beforeEach(() => resetDatabase());

/** A 9-second sample with a picture and a tone, long enough for the stretches the fake LLM picks. */
function makeSample(): string {
  const file = path.join(os.tmpdir(), `e2e-sample-${process.pid}.mp4`);
  execFileSync("ffmpeg", [
    "-v",
    "error",
    "-y",
    "-f",
    "lavfi",
    "-i",
    "testsrc2=size=540x960:rate=25:duration=9",
    "-f",
    "lavfi",
    "-i",
    "sine=frequency=440:duration=9",
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    "-c:a",
    "aac",
    "-shortest",
    file,
  ]);
  return file;
}

async function openSampleDrawer(page: Page): Promise<Locator> {
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByText("Từ video mẫu", { exact: true }).click();
  return dialog;
}

async function uploadSample(dialog: Locator) {
  await dialog.getByText("Tải video lên", { exact: true }).click();
  await dialog.locator('input[type="file"]').setInputFiles(makeSample());
  await expect(dialog.getByText(/e2e-sample-\d+\.mp4/)).toBeVisible();
}

async function scriptWritten(page: Page) {
  await expect(page.getByTestId("scene")).toHaveCount(5, { timeout: 90_000 });
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 90_000 });
}

test("Từ video mẫu: an uploaded sample writes a script with its clips, then makes another video", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  const dialog = await openSampleDrawer(page);
  await expect(dialog.getByTestId("sample-mode-help")).toContainText("Nhanh và rẻ nhất");
  await uploadSample(dialog);
  await dialog.getByLabel("Chủ đề hoặc yêu cầu cho video mới").fill("cùng kiểu này nhưng về hạt chia");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);

  await scriptWritten(page);
  const card = page.getByTestId("sample-card");
  await expect(card).toContainText(/File tải lên: e2e-sample-\d+\.mp4/);
  await expect(card).toContainText("Cách làm: Nhanh");
  // The title scene and the first two scenes got a stretch of the sample as their clip.
  await expect(page.getByTestId("title-scene").getByTestId("scene-video")).toHaveCount(1);
  await card.getByText("Xem phân tích, khung hình và lời thoại").click();
  await expect(card.getByTestId("sample-analysis")).toContainText("Hook");
  await expect(card.getByTestId("sample-frames").locator("img").first()).toBeVisible();
  await card.getByText("Lời thoại video mẫu").click();
  await expect(card).toContainText("Ba món ăn sáng tốt cho tim.");

  // Way "Dùng mẫu đã học": the same sample, nothing uploaded again.
  await card.getByRole("button", { name: "Tạo thêm video từ mẫu này" }).click();
  await expect(page).toHaveURL(/\/videos$/);
  const again = page.getByRole("dialog", { name: "Tạo video" });
  await expect(again.getByTestId("sample-mode-help")).toContainText("Không tải lại, không phân tích lại");
  await expect(again.getByTestId("chosen-sample")).toContainText("Hook");
  await again.getByLabel("Chủ đề hoặc yêu cầu cho video mới").fill("cùng kiểu này nhưng về yến mạch");
  await again.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);
  await scriptWritten(page);
  await expect(page.getByTestId("sample-card")).toContainText("Cách làm: Dùng mẫu đã học");
});

test("Edit từ footage: the footage is cut by its words into scenes that keep their own sound", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  const dialog = await openSampleDrawer(page);
  await chooseOption(page, dialog.getByLabel("Cách làm"), "Edit từ footage");
  await expect(dialog.getByTestId("sample-mode-help")).toContainText("giữ nguyên tiếng gốc");
  await uploadSample(dialog);
  await dialog.getByLabel("Tiêu đề video").fill("Review *yến mạch* Úc");
  await dialog.getByRole("button", { name: "Dựng từ footage" }).click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);

  // The fake ElevenLabs says two sentences 1.5 s apart: the title scene and one scene, each a stretch of the footage.
  await expect(page.getByTestId("scene")).toHaveCount(1, { timeout: 90_000 });
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 90_000 });
  await expect(page.getByTestId("sample-card")).toContainText("Cách làm: Edit từ footage");
  await expect(page.getByTestId("title-scene").getByTestId("scene-video")).toHaveCount(1);

  // "Cắt video" shows the clip's sound kept for the MP4, captions following its words.
  const scene = page.getByTestId("scene").first();
  await scene.getByRole("button", { name: "Cắt video" }).click();
  const trim = page.getByRole("dialog", { name: "Cắt video cảnh" });
  await expect(trim.getByRole("switch", { name: "Giữ tiếng gốc khi xuất video" })).toBeChecked();
  await expect(trim.getByTestId("trim-sound-note")).toContainText("phụ đề chạy theo lời nói");
});

test("Từ video mẫu, Duyệt phân tích trước: the edited analysis is saved, then the script is written", async ({
  page,
}) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  const dialog = await openSampleDrawer(page);
  await chooseOption(page, dialog.getByLabel("Cách làm"), "Duyệt phân tích trước");
  await expect(dialog.getByTestId("sample-mode-help")).toContainText("bạn đọc và sửa bản phân tích");
  await uploadSample(dialog);
  await dialog.getByLabel("Chủ đề hoặc yêu cầu cho video mới").fill("ba món ăn sáng cho người huyết áp cao");
  await dialog.getByRole("button", { name: "Phân tích video mẫu" }).click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);

  // The job stops after the analysis and waits for a member: no script yet.
  const review = page.getByTestId("sample-review");
  const analysis = review.getByLabel("Bản phân tích video mẫu");
  await expect(analysis).toHaveValue(/Hook/, { timeout: 90_000 });
  await expect(page.getByTestId("scene")).toHaveCount(0);
  await analysis.fill("Hook: câu hỏi ở giây đầu.\nGiữ hook, bỏ đoạn cuối.");
  await review.getByRole("button", { name: "Viết kịch bản" }).click();

  await scriptWritten(page);
  const card = page.getByTestId("sample-card");
  await expect(card).toContainText("Cách làm: Duyệt phân tích trước");
  await card.getByText("Xem phân tích, khung hình và lời thoại").click();
  await expect(card.getByTestId("sample-analysis")).toContainText("Giữ hook, bỏ đoạn cuối.");
});

test("Kho kiến thức: the sample video prompts show their default until a group saves its own", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Kho kiến thức" }).click();
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const health = page.locator('[data-topic="Sức khỏe"]');
  const learn = health.getByLabel("Prompt học từ video mẫu", { exact: true });
  const analyze = health.getByLabel("Prompt phân tích video mẫu", { exact: true });
  const learnItem = health.getByRole("tab", { name: /^Học từ video mẫu/ });
  const analyzeItem = health.getByRole("tab", { name: /^Phân tích video mẫu/ });
  await health.getByRole("tab", { name: "Prompt", exact: true }).click();
  await learnItem.click();
  await expect(learn).toHaveValue(/^Bạn là biên kịch video ngắn/);
  await expect(learnItem).toContainText("Mặc định");
  await analyzeItem.click();
  await expect(analyze).toHaveValue(/^Bạn là chuyên gia phân tích video ngắn/);

  await learnItem.click();
  await learn.fill("Học video mẫu cho [chủ đề]");
  const learnCard = health.locator(".ant-card").filter({ hasText: "Prompt học từ video mẫu" });
  await learnCard.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(page.getByText("Đã lưu prompt học từ video mẫu")).toBeVisible();
  await expect(learnItem).toContainText("Đã sửa");
  await page.reload();
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  await health.getByRole("tab", { name: "Prompt", exact: true }).click();
  await learnItem.click();
  await expect(learn).toHaveValue("Học video mẫu cho [chủ đề]");
  await analyzeItem.click();
  await expect(analyze).toHaveValue(/^Bạn là chuyên gia phân tích video ngắn/);
});
