import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
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

  // A scene with a voice text reads only that; emptied, it says it reads its on-screen text, cleaned for speech.
  await expect(first.getByText("Sẽ đọc chữ trên màn hình")).toHaveCount(0);
  const second = scenes.nth(1);
  const voice = second.getByLabel("Lời đọc");
  await voice.fill("");
  await voice.blur();
  await expect(second.getByText(/Sẽ đọc chữ trên màn hình: .+\. Giàu canxi\./)).toBeVisible();

  await page.getByRole("button", { name: "Render" }).click();
  await expect(page.getByTestId("video-status")).toHaveText("Xong", { timeout: 120_000 });
  // A script's scenes follow their narration ("Tự khớp lời đọc"): each lasts its fake narration of 0.3 s per word plus
  // 0.6 s and the MP3 padding, shorter or longer than it was set to: the title's 6 words take 2.5 s (it was set to 3),
  // the five scenes' 4 words 1.9 s each.
  await expect(page.getByTestId("render-time")).toContainText("Dài 12,0 giây");
  await expect(first.getByTestId("voice-player")).toBeVisible();

  // The tab the member picked stays picked after the render; the MP4 is under "Xuất bản".
  await page.getByRole("tab", { name: "Xuất bản" }).click();
  // The MP4 plays at the listener's volume, set under it: the player is too narrow for the browser's slider.
  const mp4 = page.getByTestId("mp4-player");
  await page.getByTestId("listen-volume").getByRole("button", { name: "Tắt tiếng" }).click();
  await expect.poll(() => mp4.evaluate((element: HTMLVideoElement) => element.muted)).toBe(true);
  await page.getByTestId("listen-volume").getByRole("button", { name: "Bật tiếng" }).click();
  await expect.poll(() => mp4.evaluate((element: HTMLVideoElement) => element.muted)).toBe(false);
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

  await openPublish(page);
  await page.getByRole("dialog", { name: "Đăng bài" }).getByRole("button", { name: "Đăng", exact: true }).click();
  await expect(page.getByTestId("publication-status")).toHaveText("Đã đăng lên Facebook", { timeout: 30_000 });
  await expect(page.getByRole("link", { name: "Xem Reel" })).toHaveAttribute("href", /facebook\.com\/reel\//);

  // Once posted, the card says so rather than the video's own "Xong".
  await page.goto("/videos");
  const card = page.getByTestId("video-card").first();
  await expect(card.getByTestId("video-status")).toHaveText("Đã đăng");
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
  const bar = page.getByTestId("render-bar");
  await expect(bar.getByTestId("render-bar-summary")).toContainText("5 cảnh");
  await expect(bar.getByTestId("render-bar-summary")).toContainText("chưa có MP4");
  await page.getByRole("button", { name: "Render" }).click();
  // The bar says the render is on its way, wherever the member has scrolled, and when it is done.
  await expect(bar.getByTestId("render-bar-job")).toBeVisible();
  await expect(page.getByText("Đã render xong MP4")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("video-status")).toHaveText("Xong");
  await expect(bar.getByTestId("render-bar-job")).toHaveCount(0);
  await expect(bar).toContainText("MP4 đã theo bản mới nhất.");
  await expect(bar.getByRole("button", { name: "Render lại" })).toBeEnabled();

  await openPublish(page);
  await page.getByRole("radio", { name: "Hẹn giờ" }).click();
  await page.getByLabel("Giờ đăng").fill(vietnamTimeIn(2));
  await page.getByRole("dialog", { name: "Đăng bài" }).getByRole("button", { name: "Đăng", exact: true }).click();
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
  await expect(bar.getByTestId("render-bar-outdated")).toBeVisible();
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
  // A group opens on its videos; the prompts are one tab, each prompt chosen on its left.
  await expect(health.getByRole("tab", { name: /^Video/ })).toHaveAttribute("aria-selected", "true");
  await health.getByRole("tab", { name: "Prompt", exact: true }).click();
  const scriptCard = health.locator(".ant-card").filter({ hasText: "Prompt viết kịch bản" });
  const cloneCard = health.locator(".ant-card").filter({ hasText: "Prompt nhân bản" });
  const prompt = health.getByLabel("Prompt viết kịch bản", { exact: true });
  const clonePrompt = health.getByLabel("Prompt nhân bản", { exact: true });
  const scriptItem = health.getByRole("tab", { name: /^Viết kịch bản/ });
  const cloneItem = health.getByRole("tab", { name: /^Nhân bản/ });
  await expect(prompt).toHaveValue(/Chủ đề: \[Chủ đề\]/);
  await expect(cloneItem).toContainText("Mặc định");
  await cloneItem.click();
  await expect(clonePrompt).toHaveValue(/^Video gốc: "\[tiêu đề\]"/);

  await scriptItem.click();
  await prompt.fill("   ");
  await expect(scriptCard.getByRole("button", { name: "Lưu", exact: true })).toBeDisabled();
  await prompt.fill("Prompt mới cho [Chủ đề]");
  // Unsaved text in another prompt survives this save.
  await cloneItem.click();
  await clonePrompt.fill("Biến thể của [tiêu đề] chưa lưu");
  await scriptItem.click();
  await scriptCard.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(page.getByText("Đã lưu prompt viết kịch bản")).toBeVisible();
  await expect(scriptItem).toContainText("Đã sửa");
  await expect(health).toContainText("1 prompt đã sửa");
  await cloneItem.click();
  await expect(clonePrompt).toHaveValue("Biến thể của [tiêu đề] chưa lưu");
  await cloneCard.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(page.getByText("Đã lưu prompt nhân bản")).toBeVisible();
  await health.getByRole("tab", { name: "Cài đặt nhóm" }).click();
  await health.getByLabel("Từ cấm", { exact: true }).fill("thần dược\nđặc trị");
  await health.getByRole("button", { name: "Lưu từ cấm" }).click();
  await expect(page.getByText("Đã lưu danh sách từ cấm")).toBeVisible();

  await page.getByLabel("Tên nhóm chủ đề mới").fill("Làm đẹp");
  await page.getByRole("button", { name: "Thêm nhóm" }).click();
  await page.getByRole("button", { name: /Làm đẹp/ }).click();
  const beauty = page.locator('[data-topic="Làm đẹp"]');
  await expect(beauty).toContainText("chưa có prompt viết kịch bản");
  await expect(beauty.getByText("Nhóm này chưa có video nào")).toBeVisible();
  await expect(beauty.getByRole("button", { name: "Tạo video" })).toHaveCount(0);
  await beauty.getByRole("tab", { name: "Prompt", exact: true }).click();
  await expect(beauty.getByLabel("Prompt viết kịch bản", { exact: true })).toHaveValue("");
  await expect(beauty.getByRole("tab", { name: /^Viết kịch bản/ })).toContainText("Trống");
  await beauty.getByRole("tab", { name: "Cài đặt nhóm" }).click();
  await expect(beauty.getByLabel("Từ cấm", { exact: true })).toHaveValue("");
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
  await health.getByRole("tab", { name: "Prompt", exact: true }).click();
  await expect(prompt).toHaveValue("Prompt mới cho [Chủ đề]");
  await cloneItem.click();
  await expect(clonePrompt).toHaveValue("Biến thể của [tiêu đề] chưa lưu");
  await health.getByRole("tab", { name: "Cài đặt nhóm" }).click();
  await expect(health.getByLabel("Từ cấm", { exact: true })).toHaveValue("thần dược\nđặc trị");
  await health.getByRole("tab", { name: "Prompt", exact: true }).click();
  await scriptItem.click();
  // "Lịch sử" of the prompt: who saved what, the difference, and any version (the app's default too) put back.
  await expect(health).toContainText("Nguyễn Văn An sửa Từ cấm lúc");
  await scriptCard.getByRole("button", { name: "Lịch sử" }).click();
  const history = page.getByRole("dialog", { name: "Lịch sử: Prompt viết kịch bản" });
  const latest = history.getByTestId("edit-history-entry").first();
  await expect(latest).toContainText("Nguyễn Văn An");
  await expect(latest).toContainText("Đang dùng");
  await latest.getByRole("button", { name: "Xem khác biệt" }).click();
  const diff = page.getByTestId("edit-history-diff");
  await expect(diff).toContainText("+ Prompt mới cho [Chủ đề]");
  await expect(diff).toContainText("− Bạn là biên tập viên kênh Reels dưỡng sinh cho người 40+.");
  await page
    .getByRole("dialog", { name: /Bản trước → bản này/ })
    .getByRole("button", { name: "Đóng" })
    .click();
  await expect(diff).toBeHidden();
  await history
    .getByTestId("edit-history-version")
    .filter({ hasText: "Bản mặc định của app" })
    .getByRole("button", { name: "Khôi phục bản này" })
    .click();
  await page.getByRole("dialog", { name: "Khôi phục bản này?" }).getByRole("button", { name: "Khôi phục" }).click();
  await expect(prompt).toHaveValue(/^Bạn là biên tập viên kênh Reels dưỡng sinh cho người 40\+\./);
  await expect(history.getByTestId("edit-history-entry").first()).toContainText("Khôi phục");
  await history.getByRole("button", { name: "Đóng" }).click();
  await expect(scriptCard.getByRole("button", { name: "Khôi phục mặc định" })).toHaveCount(0);
  await cloneItem.click();
  await expect(clonePrompt).toHaveValue("Biến thể của [tiêu đề] chưa lưu");
  await expect(page.getByRole("dialog")).toBeHidden();

  // Renamed in place on its heading.
  await page.getByRole("button", { name: /Làm đẹp/ }).click();
  await beauty.getByRole("button", { name: "Đổi tên" }).click();
  await beauty.getByLabel("Tên nhóm chủ đề").fill("Làm đẹp da");
  await beauty.getByRole("button", { name: "Lưu tên" }).click();
  await expect(page.getByText("Đã lưu tên nhóm chủ đề")).toBeVisible();
  await expect(page.getByRole("button", { name: /Làm đẹp da/ })).toBeVisible();
  const renamed = page.locator('[data-topic="Làm đẹp da"]');
  await renamed.getByRole("button", { name: "Thao tác khác với nhóm" }).click();
  await page.getByRole("menuitem", { name: "Xoá nhóm" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Xoá" }).click();
  await expect(page.getByRole("button", { name: /Làm đẹp/ })).toHaveCount(0);
  // A deleted group stays in the list's history.
  await page.getByRole("button", { name: "Lịch sử nhóm chủ đề" }).click();
  const groups = page.getByRole("dialog", { name: "Lịch sử: Nhóm chủ đề" });
  await expect(groups.getByTestId("edit-history-entry").first()).toContainText("Xoá");
  await expect(groups.getByTestId("edit-history-entry").first()).toContainText("“Làm đẹp da”");
  await expect(groups).toContainText("Làm đẹp → Làm đẹp da");
});

test("knowledge topics: a group's Video tab lists its videos and makes a new one in it", async ({ page }) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau mầm trồng tại nhà");
  // "Loại nội dung" is typed on the video's page; the tags beside it say how the video was made.
  const kindLine = page.getByTestId("video-kind-line");
  await expect(kindLine).toContainText("AI viết");
  await kindLine.getByLabel("Loại nội dung").fill("Hướng dẫn trồng");
  await kindLine.getByLabel("Loại nội dung").press("Enter");
  await page.reload();
  await expect(page.getByTestId("video-kind-line").getByLabel("Loại nội dung")).toHaveValue("Hướng dẫn trồng");
  // Every list shows the kind and, platform by platform, whether the video is out there yet.
  await page.goto("/videos");
  const card = page.getByTestId("video-card").first();
  await expect(card.getByTestId("video-content-type")).toHaveText("Hướng dẫn trồng");
  await expect(card.getByTestId("video-kind")).toContainText("AI viết");
  await expect(card.getByTestId("posted-platforms").locator('[data-posted="true"]')).toHaveCount(0);

  await page.goto("/knowledge");
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const videos = page.locator('[data-topic="Sức khỏe"]').getByTestId("topic-videos");
  await expect(videos.getByTestId("video-content-type")).toHaveText("Hướng dẫn trồng");
  await expect(videos.getByTestId("posted-platforms")).toHaveCount(1);
  await expect(videos.getByRole("row")).toHaveCount(2); // the header and the one video
  await expect(videos).toContainText("rau mầm trồng tại nhà");
  await videos.getByLabel("Tìm video của nhóm").fill("khong co");
  await expect(videos.getByText("Không có video nào khớp")).toBeVisible();
  await videos.getByLabel("Tìm video của nhóm").fill("rau mam");
  await expect(videos.getByRole("row")).toHaveCount(2);
  // An unposted video shows dashes for its numbers, never a zero it does not have.
  await expect(videos.getByRole("columnheader", { name: "View 48h" })).toBeVisible();
  await expect(videos.getByRole("row").nth(1)).toContainText("—");
  // "Danh sách" keeps the search, and is remembered in this browser.
  await videos.getByText("Danh sách", { exact: true }).click();
  await expect(videos.getByTestId("topic-video-card")).toHaveCount(1);
  await expect(videos.getByTestId("topic-video-numbers")).toHaveText("Chưa có số liệu đăng");
  await expect(videos.getByLabel("Tìm video của nhóm")).toHaveValue("rau mam");
  await videos.getByLabel("Tìm video của nhóm").fill("khong co");
  await expect(videos.getByText("Không có video nào khớp")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  await expect(videos.getByTestId("topic-video-card")).toHaveCount(1);
  await videos.getByText("Bảng", { exact: true }).click();
  await expect(videos.getByRole("row")).toHaveCount(2);

  // "Tạo video" on another group's tab opens the dialog on that group, not the first one.
  await page.getByLabel("Tên nhóm chủ đề mới").fill("Vườn rau");
  await page.getByRole("button", { name: "Thêm nhóm" }).click();
  const garden = page.locator('[data-topic="Vườn rau"]');
  await garden.getByRole("tab", { name: "Prompt", exact: true }).click();
  await garden.getByLabel("Prompt viết kịch bản", { exact: true }).fill("Viết kịch bản trồng rau về [Chủ đề]");
  await garden.getByRole("button", { name: "Lưu", exact: true }).first().click();
  await expect(page.getByText("Đã lưu prompt viết kịch bản")).toBeVisible();
  await garden.getByRole("tab", { name: /^Video/ }).click();
  await garden.getByTestId("topic-videos").getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  // The group's name shows in the dialog only as the chosen group (the list of groups is closed).
  await expect(dialog.getByLabel("Nhóm chủ đề")).toBeVisible();
  await expect(dialog).toContainText("Vườn rau");
  await expect(dialog).not.toContainText("Sức khỏe");
  await expect(page).toHaveURL(/\/videos$/);
});

test("knowledge topics: a group's own voice is what its new videos start with", async ({ page }) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await page.goto("/knowledge");
  await page.getByLabel("Tên nhóm chủ đề mới").fill("Già Mà Khỏe");
  await page.getByRole("button", { name: "Thêm nhóm" }).click();
  const group = page.locator('[data-topic="Già Mà Khỏe"]');
  await group.getByRole("tab", { name: "Prompt", exact: true }).click();
  await group.getByLabel("Prompt viết kịch bản", { exact: true }).fill("Viết kịch bản dưỡng sinh về [Chủ đề]");
  await group.getByRole("button", { name: "Lưu", exact: true }).first().click();
  await expect(page.getByText("Đã lưu prompt viết kịch bản")).toBeVisible();

  await group.getByRole("tab", { name: "Cài đặt nhóm" }).click();
  const card = group.locator(".ant-card").filter({ hasText: "Giọng mặc định của nhóm" });
  await expect(card).toContainText("Theo Thiết lập mặc định của người tạo");
  await expect(card.getByRole("button", { name: "Lưu giọng" })).toBeDisabled();
  await card.getByLabel("Giọng đọc").click();
  await card.getByLabel("Giọng đọc").fill("Mai");
  await page.keyboard.press("Enter");
  await card.getByRole("button", { name: "Lưu giọng" }).click();
  await expect(page.getByText("Đã lưu giọng của nhóm")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: /Già Mà Khỏe/ }).click();
  await group.getByRole("tab", { name: "Cài đặt nhóm" }).click();
  await expect(card.locator(".ant-select")).toContainText("Mai");

  // A new video of the group reads with the group's voice, with nothing set on it by hand.
  await group.getByRole("tab", { name: /^Video/ }).click();
  await group.getByTestId("topic-videos").getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("ngâm chân nước ấm");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);
  const id = page.url().split("/").pop();
  const video = await (await page.request.get(`/api/videos/${id}`)).json();
  expect(video.options.voice_id).toBe("fake-voice-mai");
});

test("knowledge topics: a group's text look from an AI suggestion is what its new videos start with", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await page.goto("/knowledge");
  await page.getByLabel("Tên nhóm chủ đề mới").fill("Chữ Riêng");
  await page.getByRole("button", { name: "Thêm nhóm" }).click();
  const group = page.locator('[data-topic="Chữ Riêng"]');
  await group.getByRole("tab", { name: "Cài đặt nhóm" }).click();
  await expect(group.getByRole("heading", { name: "Viết kịch bản & tìm ảnh" })).toBeVisible();
  await expect(group.getByRole("heading", { name: "Video mới của nhóm" })).toBeVisible();
  const card = group.getByTestId("group-text-look");
  await expect(card).toContainText("Theo Thiết lập mặc định của người tạo video");
  await expect(card.getByRole("button", { name: "Lưu chữ & phụ đề" })).toBeDisabled();

  // "AI gợi ý" is a job on the team's (fake) LLM: its looks show up once the worker has made them.
  await card.getByRole("button", { name: "AI gợi ý" }).click();
  const suggestions = card.getByTestId("text-suggestion");
  await expect(suggestions).toHaveCount(3, { timeout: 60_000 });
  await suggestions.filter({ hasText: "Nổi bật" }).getByRole("button", { name: "Dùng kiểu này" }).click();
  await expect(card.getByRole("switch", { name: "Nhóm có kiểu chữ riêng" })).toBeChecked();
  // The suggestion's box is no team style: it shows as the box in use, and can become one of the team's.
  await expect(card.getByRole("radio", { name: "Kiểu đang dùng" })).toBeChecked();
  await card.getByRole("button", { name: "Lưu thành kiểu của đội" }).click();
  const drawer = page.getByRole("dialog", { name: "Thêm kiểu hộp chữ" });
  await drawer.getByLabel("Tên kiểu").fill("Đỏ nổi bật");
  await drawer.getByRole("button", { name: "Thêm kiểu" }).click();
  await expect(card.getByRole("radio", { name: "Kiểu Đỏ nổi bật" })).toBeChecked();
  await expect(card.getByRole("radio", { name: "Kiểu đang dùng" })).toHaveCount(0);
  await card.getByRole("switch", { name: "AI chọn kiểu chữ cho từng video" }).click();
  await card.getByRole("button", { name: "Lưu chữ & phụ đề" }).click();
  await expect(page.getByText("Đã lưu chữ & phụ đề của nhóm")).toBeVisible();
  await expect(card.getByRole("button", { name: "Lưu chữ & phụ đề" })).toBeDisabled();

  const knowledge = await (await page.request.get("/api/knowledge")).json();
  const topic = knowledge.topics.find((item: { name: string }) => item.name === "Chữ Riêng");
  expect(topic.text_ai).toBe(true);
  expect(topic.text_look).toMatchObject({
    text_style: "box",
    box_color: "#E10600",
    accent_color: "#FFD400",
    captions: "word",
  });
  const made = await page.request.post("/api/videos", {
    data: { topic: "rau mầm", knowledge_topic_id: topic.id, mode: "manual", script: "Một" },
    headers: { Origin: new URL(page.url()).origin },
  });
  expect(made.ok()).toBe(true);
  const video = await made.json();
  expect(video.options).toMatchObject({ text_style: "box", box_color: "#E10600", captions: "word" });
});

test("knowledge topics: a group's video mode is what its new videos take unless one is picked", async ({ page }) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await page.goto("/knowledge");
  await page.getByLabel("Tên nhóm chủ đề mới").fill("Món Quê");
  await page.getByRole("button", { name: "Thêm nhóm" }).click();
  const group = page.locator('[data-topic="Món Quê"]');
  await group.getByRole("tab", { name: "Prompt", exact: true }).click();
  await group.getByLabel("Prompt viết kịch bản", { exact: true }).fill("Viết kịch bản món quê về [Chủ đề]");
  await group.getByRole("button", { name: "Lưu", exact: true }).first().click();
  await expect(page.getByText("Đã lưu prompt viết kịch bản")).toBeVisible();
  await group.getByRole("tab", { name: "Cài đặt nhóm" }).click();
  const card = group.locator(".ant-card").filter({ hasText: "Kiểu video của nhóm" });
  await expect(card.getByRole("radio", { name: "Slide ảnh" })).toBeChecked();
  await expect(card.getByRole("button", { name: "Lưu kiểu video" })).toBeDisabled();
  await card.getByText("Xen kẽ theo ngày (ngày lẻ: xuyên suốt, ngày chẵn: slide)").click();
  await card.getByRole("button", { name: "Lưu kiểu video" }).click();
  await expect(page.getByText("Đã lưu kiểu video của nhóm")).toBeVisible();
  await expect(card).toContainText("Hôm nay (giờ Việt Nam):");
  await card.getByText("Video xuyên suốt", { exact: true }).click();
  await card.getByRole("button", { name: "Lưu kiểu video" }).click();
  await expect(card.getByRole("button", { name: "Lưu kiểu video" })).toBeDisabled();
  await page.reload();
  await page.getByRole("button", { name: /Món Quê/ }).click();
  await group.getByRole("tab", { name: "Cài đặt nhóm" }).click();
  await expect(card.getByRole("radio", { name: "Video xuyên suốt" })).toBeChecked();

  // The dialog starts on the group's mode and says so; a video made with nothing picked takes it.
  await group.getByRole("tab", { name: /^Video/ }).click();
  await group.getByTestId("topic-videos").getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await expect(dialog).toContainText("Theo kiểu video của nhóm: Video xuyên suốt");
  await expect(
    dialog.getByLabel("Kiểu video", { exact: true }).getByRole("radio", { name: "Video xuyên suốt" }),
  ).toBeChecked();
  await dialog.getByText("Tự viết", { exact: true }).click();
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("canh chua cá lóc");
  await dialog.getByRole("button", { name: "Tạo video" }).click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);
  const id = page.url().split("/").pop();
  const video = await (await page.request.get(`/api/videos/${id}`)).json();
  expect(video.mode).toBe("single");
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

test("a scene reuses a photo another video of its group already uses", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "canxi cho người lớn tuổi");
  await newVideoWithScript(page, "rau xanh cho người lớn tuổi");

  await page.getByTestId("scene").first().getByRole("button", { name: "Chọn từ kho" }).click();
  await page.getByRole("menuitem", { name: "Đã dùng trong nhóm" }).click();
  const picker = page.getByRole("dialog", { name: "Ảnh/video đã dùng trong nhóm" });
  const items = picker.getByTestId("group-media-item");
  await expect(items.first()).toBeVisible();
  await picker.getByLabel("Tìm ảnh đã dùng").fill("khong co tu nay");
  await expect(picker.getByText("Không có ảnh nào khớp")).toBeVisible();
  await picker.getByLabel("Tìm ảnh đã dùng").fill("");
  // The scene has its own photo already, so using another one asks first.
  await items.first().getByRole("button", { name: "Dùng" }).click();
  await page
    .getByRole("dialog", { name: "Thay ảnh/video hiện tại của cảnh này?" })
    .getByRole("button", { name: "Đổi" })
    .click();
  await expect(page.getByText("Đã dùng cho cảnh này")).toBeVisible();
  await expect(picker).toBeHidden();
});

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
  await chooseOption(page, page.getByLabel("Người tạo"), "Của tôi");
  await expect(cards).toHaveCount(1);
  await chooseOption(page, page.getByLabel("Lọc theo nhóm chủ đề"), "Sức khỏe (1)");
  await expect(cards).toHaveCount(1);

  // The list view shows one row per video; the choice, and the topic group, are remembered in this browser.
  await page.getByTitle("Dạng danh sách").click();
  await expect(page.getByTestId("video-row")).toHaveCount(1);
  await page.reload();
  await expect(page.getByTestId("video-row")).toHaveCount(1);
  await expect(page.locator(".ant-select").filter({ has: page.getByLabel("Lọc theo nhóm chủ đề") })).toContainText(
    "Sức khỏe",
  );
  await page.getByTestId("video-row").first().click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);
  await page.goto("/videos");
  await page.getByTitle("Dạng lưới").click();
  await expect(cards).toHaveCount(1);
});

test("video list: Cần làm, the group's week, and a TikTok nudge on a card doing well", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "canxi cho người lớn tuổi");
  // How the list reads the video, without rendering and posting it for real: as it is, rendered and waiting, or out
  // on a Page at 4× its median at 48 hours.
  let as: "draft" | "done" | "posted" = "draft";
  await page.route(
    (url) => url.pathname === "/api/videos",
    async (route) => {
      const response = await route.fetch();
      const rows = await response.json();
      if (as !== "draft") {
        rows[0] = { ...rows[0], status: "done", status_label: "Xong" };
      }
      if (as === "posted") {
        rows[0].post = {
          state: "posted",
          fanpage: "Vườn nhà",
          fanpages: ["Vườn nhà"],
          pages: 1,
          at: new Date().toISOString(),
          views: 4000,
          shares: 40,
          share_rate: 0.01,
          share_met: false,
          times_median: 4,
        };
      }
      await route.fulfill({ response, json: rows });
    },
  );
  await page.goto("/videos");
  const cards = page.getByTestId("video-card");
  await expect(cards).toHaveCount(1);

  // A draft made today is not yet "Cần làm"; the group's line counts this week's videos.
  await chooseOption(page, page.getByLabel("Lọc theo trạng thái"), "Cần làm");
  await expect(cards).toHaveCount(0);
  await chooseOption(page, page.getByLabel("Lọc theo nhóm chủ đề"), "Sức khỏe (1)");
  await expect(page.getByTestId("group-week")).toHaveText(
    "Sức khỏe, tuần này (từ thứ Hai): 1 video mới, 0 đã đăng, 1 còn nháp",
  );

  // Rendered and not posted anywhere: it waits on someone.
  as = "done";
  await page.reload();
  await chooseOption(page, page.getByLabel("Lọc theo trạng thái"), "Cần làm");
  await expect(cards).toHaveCount(1);
  await expect(page.getByTestId("card-make-tiktok")).toHaveCount(0);

  // Out and doing well: no longer to do, and the card offers a TikTok version, which opens the clone drawer.
  as = "posted";
  await page.reload();
  // The filter stays in the address over the reload: still on "Cần làm", where the video no longer is.
  await expect(page).toHaveURL(/[?&]status=todo/);
  await expect(cards).toHaveCount(0);
  await expect(page.getByTestId("group-week")).toContainText("1 đã đăng, 0 còn nháp");
  await page.goto("/videos");
  const nudge = page.getByTestId("card-make-tiktok");
  await expect(nudge).toHaveText("Tạo bản TikTok");
  await nudge.click();
  await expect(page.getByRole("dialog", { name: "Tạo bản TikTok" })).toBeVisible();
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
  await expect(first.getByTestId("word-count").first()).toHaveText("11 từ, nên tối đa 10 từ");
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

test("Sửa ảnh: erase a drawn box, edit in words, then bring back the original", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau xanh cho người lớn tuổi");
  const first = page.getByTestId("scene").first();
  const preview = first.getByTestId("scene-preview");
  const original = await preview.getAttribute("src");

  // "Xóa vùng": nothing to erase until a box is drawn over the photo.
  await first.getByRole("button", { name: "Sửa ảnh" }).click();
  const dialog = page.getByRole("dialog", { name: "Sửa ảnh cảnh", exact: true });
  const erase = dialog.getByRole("button", { name: "Xóa vùng đã khoanh" });
  await expect(erase).toBeDisabled();
  const photo = dialog.getByRole("img", { name: "Ảnh của cảnh" });
  await expect.poll(() => photo.evaluate((element: HTMLImageElement) => element.naturalWidth)).toBeGreaterThan(0);
  const area = (await dialog.getByTestId("image-edit-canvas").boundingBox())!;
  await page.mouse.move(area.x + area.width * 0.3, area.y + area.height * 0.4);
  await page.mouse.down();
  await page.mouse.move(area.x + area.width * 0.6, area.y + area.height * 0.5, { steps: 5 });
  await page.mouse.up();
  await expect(dialog.getByTestId("edit-box")).toHaveCount(1);
  await expect(dialog.getByTestId("edit-box-count")).toHaveText("Đã khoanh 1 vùng");
  // LaMa runs only in the worker image; here the fake Cloudflare paints the box.
  await dialog.getByRole("radio", { name: /Cloudflare/ }).check();
  await erase.click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 120_000 });
  await expect(preview).not.toHaveAttribute("src", original ?? "", { timeout: 30_000 });
  await expect(first.getByTestId("image-edited")).toBeVisible();

  // "Sửa theo mô tả": Gemini edits the photo as asked, the original is still kept.
  const erased = await preview.getAttribute("src");
  await first.getByRole("button", { name: "Sửa ảnh" }).click();
  await dialog.getByRole("tab", { name: "Sửa theo mô tả" }).click();
  await dialog.getByLabel("Điều cần sửa trên ảnh").fill("làm nền sáng hơn");
  await dialog.getByRole("button", { name: "Sửa ảnh", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 120_000 });
  await expect(preview).not.toHaveAttribute("src", erased ?? "", { timeout: 30_000 });

  // "Khôi phục ảnh gốc" brings back the photo from before the first edit.
  await first.getByRole("button", { name: "Khôi phục ảnh gốc" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Khôi phục" }).click();
  await expect(first.getByTestId("image-edited")).toHaveCount(0);
  await expect(preview).toHaveAttribute("src", original ?? "");
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
  // "Chỉnh cảnh 2": its seconds are at hand here; the page is not in "Chỉnh sửa", so they only show.
  const editor = preview.getByTestId("preview-scene-editor");
  await expect(editor).toContainText("Chỉnh cảnh 2");
  await expect(editor.getByLabel("Số giây của cảnh")).toBeVisible();

  // The timeline: a ruler in seconds and a playhead that goes to any second, paused there.
  const timeline = preview.getByTestId("preview-timeline");
  await expect(timeline.getByTestId("timeline-ruler")).toContainText("00:00");
  const playhead = timeline.getByRole("slider", { name: "Đầu phát" });
  await playhead.focus();
  await page.keyboard.press("Home");
  // Reached and moved from the keyboard, it shows where the focus is.
  await expect(playhead).toHaveCSS("outline-style", "solid");
  await expect(now).toContainText("Cảnh tiêu đề");
  await expect(timeline.getByTestId("preview-time")).toHaveText("00:00,0");
  await expect(preview.getByRole("button", { name: "Tiếp tục" })).toBeVisible();
  await page.keyboard.press("End");
  await expect(now).toContainText("Cảnh 5");
  await page.keyboard.press("Home");
  for (let step = 0; step < 3; step += 1) await page.keyboard.press("ArrowRight");
  await expect(timeline.getByTestId("preview-time")).toHaveText("00:01,5");
  await expect(preview.getByRole("button", { name: "Tiếp tục" })).toBeVisible();
  // Zooming in spreads the scenes wider than the timeline, which then scrolls.
  const viewport = timeline.getByTestId("timeline-viewport");
  await timeline.getByRole("button", { name: "Phóng to thanh thời gian" }).click();
  await timeline.getByRole("button", { name: "Phóng to thanh thời gian" }).click();
  await expect.poll(() => viewport.evaluate((element) => element.scrollWidth > element.clientWidth + 10)).toBe(true);
  await timeline.getByRole("button", { name: "Thu nhỏ thanh thời gian" }).click();
  await timeline.getByRole("button", { name: "Thu nhỏ thanh thời gian" }).click();
  await expect.poll(() => viewport.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);

  // The app frame and the safe zone are under "Khung" in the tools column.
  await preview.getByRole("tab", { name: "Khung" }).click();
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

  // "Tạo giọng ElevenLabs": the fake reads the scenes without narration, after a confirmation.
  await preview.getByRole("tab", { name: "Giọng đọc" }).click();
  const voiceBox = preview.getByTestId("preview-voice");
  await expect(voiceBox).toContainText("chưa có giọng ElevenLabs");
  await expect(voiceBox.getByLabel("Giọng đọc")).toBeVisible();
  await voiceBox.getByRole("button", { name: /^Tạo giọng ElevenLabs cho \d+ cảnh$/ }).click();
  await page.getByRole("button", { name: "Tạo giọng", exact: true }).click();
  // Once every scene has its narration, the button goes and the voice choice stays.
  await expect(voiceBox).toContainText("Mọi cảnh đã có giọng ElevenLabs", { timeout: 60_000 });
  await expect(voiceBox.getByRole("button", { name: /^Tạo giọng ElevenLabs/ })).toHaveCount(0);

  // The listener's own volume: muting and the slider change what plays here, never the video's settings.
  const narration = preview.getByTestId("preview-narration");
  const volume = () => narration.evaluate((element: HTMLAudioElement) => element.volume);
  await expect.poll(volume).toBe(1);
  await preview.getByRole("button", { name: "Tắt tiếng" }).click();
  await expect.poll(volume).toBe(0);
  await preview.getByRole("button", { name: "Bật tiếng" }).click();
  await expect.poll(volume).toBe(1);
  const slider = preview.getByRole("slider", { name: "Âm lượng nghe" });
  await slider.focus();
  for (let step = 0; step < 50; step += 1) await page.keyboard.press("ArrowLeft");
  await expect(slider).toHaveAttribute("aria-valuenow", "50");
  await expect.poll(volume).toBeCloseTo(0.5);
  // Remembered in this browser, for every player.
  await page.reload();
  await page.getByTestId("render-bar").getByRole("button", { name: "Xem trước" }).click();
  preview = page.getByRole("dialog", { name: "Xem trước video" });
  await expect(preview.getByRole("slider", { name: "Âm lượng nghe" })).toHaveAttribute("aria-valuenow", "50");
});

test("studio: tracks under the scenes, a locked track, and a scene split at the playhead then undone", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau mầm trồng tại nhà");
  await page.getByTestId("render-bar").getByRole("button", { name: "Xem trước" }).click();
  const studio = page.getByRole("dialog", { name: "Xem trước video" });
  await studio.getByRole("button", { name: "Tạm dừng" }).click();

  // The tracks under the scenes: each scene's text, and its narration, dashed while only the browser reads it.
  const timeline = studio.getByTestId("preview-timeline");
  const names = timeline.getByTestId("timeline-tracks");
  await expect(names).toContainText("Cảnh");
  await expect(names).toContainText("Chữ");
  await expect(names).toContainText("Giọng");
  await expect(timeline.getByTestId("lane-text")).toHaveCount(6);
  await expect(timeline.getByTestId("lane-voice").first()).toHaveAttribute("aria-label", /^Giọng: Giọng tạm: /);
  // A block of a track plays its scene.
  await timeline.getByTestId("lane-text").nth(2).click();
  await expect(studio.getByTestId("preview-scene")).toContainText("Cảnh 2");
  await studio.getByRole("button", { name: "Tạm dừng" }).click();

  // Cảnh 1 made 4 seconds long, then the playhead 1.5 to 2 seconds into it.
  await timeline.getByRole("button", { name: "Xem Cảnh 1" }).click();
  await studio.getByRole("button", { name: "Tạm dừng" }).click();
  const seconds = studio.getByTestId("preview-scene-editor").getByLabel("Số giây của cảnh");
  await seconds.fill("4");
  await seconds.press("Enter");
  await expect(timeline.getByRole("button", { name: "Xem Cảnh 1" })).toContainText("4s");
  const titleLabel = await timeline.getByRole("button", { name: "Xem Cảnh tiêu đề" }).innerText();
  const titleSeconds = Number(titleLabel.match(/([\d,]+)s/)![1].replace(",", "."));
  const playhead = timeline.getByRole("slider", { name: "Đầu phát" });
  await playhead.focus();
  await page.keyboard.press("Home");
  for (let step = 0; step < Math.ceil((titleSeconds + 1.5) / 0.5); step += 1) await page.keyboard.press("ArrowRight");
  await expect(studio.getByTestId("preview-scene")).toContainText("Cảnh 1");

  // Locked, the scenes' track keeps "Tách cảnh" and the seconds' edges out of reach.
  const toolbar = studio.getByTestId("preview-toolbar");
  const split = toolbar.getByRole("button", { name: "Tách cảnh tại đầu phát (S)" });
  await expect(split).toBeEnabled();
  await names.getByRole("button", { name: "Khoá tầng Cảnh" }).click();
  await expect(split).toBeDisabled();
  await expect(timeline.getByTestId("timeline-edge")).toHaveCount(0);
  await expect(studio.getByTestId("preview-locked")).toBeVisible();
  await names.getByRole("button", { name: "Mở khoá tầng Cảnh" }).click();
  await expect(timeline.getByTestId("timeline-edge")).toHaveCount(6);

  // S splits Cảnh 1 at the playhead: its rest becomes a new scene of the same picture, without text.
  await playhead.focus();
  await page.keyboard.press("s");
  await expect(timeline.getByRole("button", { name: /^Xem Cảnh \d$/ })).toHaveCount(6);
  await expect(timeline.getByTestId("lane-text")).toHaveCount(6);
  await expect(page.getByTestId("scene")).toHaveCount(6);
  // "Hoàn tác" puts the scene back whole.
  await page.keyboard.press("Control+z");
  await expect(timeline.getByRole("button", { name: /^Xem Cảnh \d$/ })).toHaveCount(5);
  await expect(page.getByTestId("scene")).toHaveCount(5);

  // "Chỉnh cảnh 1" beside the phone holds the scene card's own fields: text typed here is the card's text too.
  const inspector = studio.getByTestId("preview-scene-editor");
  await expect(inspector).toContainText("Chỉnh cảnh 1");
  const text = inspector.getByLabel("Chữ trên màn hình");
  await text.fill("Rau mầm *tươi* mỗi ngày");
  await text.blur();
  await expect(inspector.getByText("Đã lưu")).toBeVisible();
  await expect(timeline.getByTestId("lane-text").nth(1)).toHaveText("Rau mầm tươi mỗi ngày");
  await expect(page.getByTestId("scene").first().getByLabel("Chữ trên màn hình")).toHaveValue(
    "Rau mầm *tươi* mỗi ngày",
  );
  // Its photo's actions are here too, and the search terms fold away until opened.
  await expect(inspector.getByRole("button", { name: "Chọn từ kho" })).toBeVisible();
  await inspector.getByText("Tìm ảnh: từ khoá và prompt AI").click();
  await expect(inspector.getByLabel("Từ khóa tìm ảnh")).toBeVisible();
  // The keys and how to edit sit behind "Phím tắt".
  await studio.getByRole("button", { name: "Phím tắt" }).click();
  await expect(page.getByTestId("preview-shortcuts")).toContainText("S: tách cảnh tại đầu phát");
});

test("studio effects: a scene's own transition and colour, drawn on the phone and undone", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau mầm trồng tại nhà");
  await page.getByTestId("render-bar").getByRole("button", { name: "Xem trước" }).click();
  const studio = page.getByRole("dialog", { name: "Xem trước video" });
  await studio.getByRole("button", { name: "Tạm dừng" }).click();
  const inspector = studio.getByTestId("preview-scene-editor");

  // The title scene opens the video and is its cover: no effects of its own.
  await expect(inspector).toContainText("không có chuyển cảnh hay màu riêng");

  await studio.getByRole("button", { name: "Xem Cảnh 2" }).click();
  await studio.getByRole("button", { name: "Tạm dừng" }).click();
  const effects = inspector.getByTestId("scene-effects");
  const transition = effects.getByLabel("Chuyển cảnh vào cảnh này");
  await expect(effects).toContainText("Theo cả video (Mờ dần)");
  await chooseOption(page, transition, "Mở vòng tròn");
  await expect(effects).toContainText("Mở vòng tròn");

  // A colour preset is drawn on the phone's picture, the text box left as it is.
  const colors = effects.getByRole("group", { name: "Màu của cảnh" });
  await colors.getByRole("button", { name: "Đen trắng" }).click();
  await expect(colors.getByRole("button", { name: "Đen trắng" })).toHaveAttribute("aria-pressed", "true");
  const picture = studio.getByTestId("preview-stage").locator("[data-color]");
  await expect(picture).toHaveAttribute("data-color", "mono");
  await expect.poll(() => picture.evaluate((element) => getComputedStyle(element).filter)).toContain("saturate(0)");

  // "Hoàn tác" takes the colour back off, then the transition.
  await page.keyboard.press("Control+z");
  await expect(colors.getByRole("button", { name: "Gốc" })).toHaveAttribute("aria-pressed", "true");
  await expect(picture).toHaveCount(0);
  await page.keyboard.press("Control+z");
  await expect(effects).toContainText("Theo cả video (Mờ dần)");
});

test("studio layers: a sticker and a text over a scene, changed, removed with Delete and put back", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau mầm trồng tại nhà");
  await page.getByTestId("render-bar").getByRole("button", { name: "Xem trước" }).click();
  const studio = page.getByRole("dialog", { name: "Xem trước video" });
  await studio.getByRole("button", { name: "Tạm dừng" }).click();
  const timeline = studio.getByTestId("preview-timeline");
  await expect(timeline.getByTestId("timeline-tracks")).toContainText("Lớp");

  // Not on the title scene: it is the video's cover.
  await studio.getByRole("tab", { name: "Chữ & sticker" }).click();
  const tools = studio.getByTestId("layer-tools");
  await expect(tools.getByRole("button", { name: "Thêm chữ" })).toBeDisabled();

  await timeline.getByRole("button", { name: "Xem Cảnh 1" }).click();
  await studio.getByRole("button", { name: "Tạm dừng" }).click();
  await tools.getByRole("button", { name: "Thêm sticker Trái tim" }).click();
  await tools.getByRole("button", { name: "Thêm chữ" }).click();
  const layers = studio.getByTestId("preview-stage").getByTestId("preview-layer");
  await expect(layers).toHaveCount(2);
  await expect(layers.first()).toBeVisible();
  await expect(timeline.getByTestId("lane-layers")).toHaveCount(2);

  // The text just added is open in "Chỉnh cảnh 1": its words and its look.
  const inspector = studio.getByTestId("preview-scene-editor");
  const words = inspector.getByLabel("Chữ của lớp", { exact: true });
  await words.fill("Giảm *50%*");
  await words.blur();
  await expect(timeline.getByTestId("lane-layers").nth(1)).toHaveText("Chữ: Giảm 50%");
  await chooseOption(page, inspector.getByLabel("Kiểu chữ của lớp"), "Hộp vàng");
  // A new look is a new picture from the api.
  const textPicture = layers.nth(1);
  await expect(inspector.getByTitle("Hộp vàng", { exact: true })).toBeVisible();
  await expect(textPicture).toHaveAttribute("src", /image\.png\?v=/);

  // Delete takes the picked layer, not the scene; Ctrl+Z puts it back.
  await timeline.getByRole("slider", { name: "Đầu phát" }).focus();
  await page.keyboard.press("Delete");
  await expect(timeline.getByTestId("lane-layers")).toHaveCount(1);
  await expect(page.getByTestId("scene")).toHaveCount(5);
  await expect(studio.getByRole("button", { name: "Hoàn tác: xoá lớp (Ctrl+Z)" })).toBeVisible();
  await page.keyboard.press("Control+z");
  await expect(timeline.getByTestId("lane-layers")).toHaveCount(2);

  // Locked, the layers' track takes no new layer.
  await timeline.getByTestId("timeline-tracks").getByRole("button", { name: "Khoá tầng Lớp" }).click();
  await expect(tools.getByRole("button", { name: "Thêm sticker Trái tim" })).toBeDisabled();
});

test("half-frame photo: only on a backdrop video, the scene's dish photo across the frame, moved only up and down", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau dền trứng gà");
  const file = path.join(os.tmpdir(), `e2e-half-photo-${process.pid}.jpg`);
  execFileSync("ffmpeg", [
    "-v",
    "error",
    "-y",
    "-f",
    "lavfi",
    "-i",
    "testsrc2=size=1600x1200:rate=1",
    "-frames:v",
    "1",
    file,
  ]);
  const card = page.getByTestId("scene").first();
  // A slide video stays as it was: no half-frame photo.
  await expect(card.getByTestId("half-photo-panel")).toHaveCount(0);
  await page.getByTestId("video-mode").getByText("Video xuyên suốt").click();
  await page.getByRole("button", { name: "Đổi", exact: true }).click();

  // Over the backdrop: added, then its photo is the scene's own, chosen with the scene's usual picture tools.
  const panel = card.getByTestId("half-photo-panel");
  await panel.getByRole("switch", { name: "Thêm ảnh chèn" }).click();
  await expect(panel.getByTestId("half-photo-scene-tools")).toBeVisible();
  await card.getByLabel("Tải ảnh/video lên cho cảnh", { exact: true }).setInputFiles(file);

  // As wide as the frame, 38% tall, flush with the top edge.
  const stage = panel.getByTestId("half-photo-stage");
  const photo = stage.getByTestId("preview-layer");
  await expect(photo).toBeVisible();
  const place = () => photo.evaluate((element) => [element.style.left, element.style.top, element.style.width]);
  await expect.poll(place).toEqual(["0%", "0%", "100%"]);

  // A quick choice, then a drag up and sideways: it stays across the frame and snaps to the top edge.
  await panel.getByLabel("Vị trí ảnh chèn").getByText("Dưới").click();
  // Flush with the bottom edge: 1920 - 730 px down the frame.
  await expect
    .poll(async () => (await place()).map(parseFloat).map((value) => Math.round(value * 10) / 10))
    .toEqual([0, 62, 100]);
  // The mouse acts on the screen: the card's frame is brought into view first.
  await stage.scrollIntoViewIfNeeded();
  const box = (await stage.boundingBox())!;
  const from = (await photo.boundingBox())!;
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  // Up past the top half: kept there.
  await page.mouse.move(from.x + from.width / 2 + 30, from.y + from.height / 2 - box.height * 0.55, { steps: 8 });
  await page.mouse.up();
  await expect.poll(place).toEqual(["0%", "0%", "100%"]);
});

test("studio sounds: a sound effect added at the playhead, heard, made louder and undone", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau mầm trồng tại nhà");
  await page.getByTestId("render-bar").getByRole("button", { name: "Xem trước" }).click();
  const studio = page.getByRole("dialog", { name: "Xem trước video" });
  await studio.getByRole("button", { name: "Tạm dừng" }).click();
  const timeline = studio.getByTestId("preview-timeline");
  await expect(timeline.getByTestId("timeline-tracks")).toContainText("Âm");

  // Each sound is made by the api with the render's own FFmpeg filters, to hear before adding it.
  const heard = await page.request.get("/api/sounds/library/ding.mp3");
  expect(heard.status()).toBe(200);
  expect(heard.headers()["content-type"]).toBe("audio/mpeg");

  await timeline.getByRole("button", { name: "Xem Cảnh 2" }).click();
  await studio.getByRole("button", { name: "Tạm dừng" }).click();
  await studio.getByRole("tab", { name: "Âm thanh" }).click();
  await studio.getByTestId("sound-tools").getByRole("button", { name: "Thêm âm Ting" }).click();
  await expect(timeline.getByTestId("lane-sounds")).toHaveCount(1);
  await expect(timeline.getByTestId("lane-sounds")).toHaveText("Ting");

  // "Âm thanh (1)" in "Chỉnh cảnh 2": its level.
  const inspector = studio.getByTestId("preview-scene-editor");
  await expect(inspector).toContainText("Âm thanh (1)");
  const row = inspector.getByTestId("sound-row");
  await row.getByText("To", { exact: true }).click();
  await expect(row.getByRole("radio", { name: "To" })).toBeChecked();

  // "Hoàn tác" twice: back to "Vừa", then the sound is gone.
  await timeline.getByRole("slider", { name: "Đầu phát" }).focus();
  await page.keyboard.press("Control+z");
  await expect(row.getByRole("radio", { name: "Vừa" })).toBeChecked();
  await expect(studio.getByRole("button", { name: "Hoàn tác: thêm âm (Ctrl+Z)" })).toBeVisible();
  await page.keyboard.press("Control+z");
  await expect(timeline.getByTestId("lane-sounds")).toHaveCount(0);
});

test("studio notes: a comment at the playhead, sent to the AI, which fixes the scene and answers", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau mầm trồng tại nhà");
  await page.getByTestId("render-bar").getByRole("button", { name: "Xem trước" }).click();
  const studio = page.getByRole("dialog", { name: "Xem trước video" });
  await studio.getByRole("button", { name: "Tạm dừng" }).click();
  const timeline = studio.getByTestId("preview-timeline");
  await timeline.getByRole("button", { name: "Xem Cảnh 2" }).click();
  await studio.getByRole("button", { name: "Tạm dừng" }).click();

  // Typed under the timeline, kept at the playhead's second, shown as a dot on the ruler.
  const box = studio.getByLabel("Góp ý tại đầu phát");
  await box.fill("Chữ cảnh này dài quá, thêm dòng giảm giá");
  await box.press("Enter");
  await expect(box).toHaveValue("");
  await expect(timeline.getByTestId("note-mark")).toHaveCount(1);
  await studio.getByRole("tab", { name: "Góp ý" }).click();
  const tools = studio.getByTestId("note-tools");
  await expect(tools.getByTestId("note")).toContainText("Chưa gửi");

  // "Nhờ AI sửa" asks first (it costs an AI call), then the job changes Cảnh 2 and answers the note.
  await tools.getByRole("button", { name: "Nhờ AI sửa (1 góp ý)" }).click();
  await page.getByRole("button", { name: "Gửi", exact: true }).click();
  await expect(tools.getByTestId("note")).toContainText("Đã sửa", { timeout: 60_000 });
  await expect(tools.getByTestId("note-reply")).toHaveText("↳ Đã sửa theo góp ý 1.");
  await expect(timeline.getByTestId("lane-text").nth(2)).toHaveText("Đã sửa theo góp ý");
  await expect(timeline.getByTestId("lane-layers")).toHaveCount(1);
  await expect(page.getByTestId("scene").nth(1).getByLabel("Chữ trên màn hình")).toHaveValue("Đã sửa\n*theo góp ý*");
});

test("knowledge topics: a group's own template dresses its new videos, over its maker's", async ({ page }) => {
  await loginAsSeed(page);
  await page.goto("/knowledge");
  await page.getByLabel("Tên nhóm chủ đề mới").fill("Mẫu riêng");
  await page.getByRole("button", { name: "Thêm nhóm" }).click();
  const group = page.locator('[data-topic="Mẫu riêng"]');
  await group.getByRole("tab", { name: "Cài đặt nhóm" }).click();
  const card = group.locator(".ant-card").filter({ hasText: "Mẫu dựng của nhóm" });
  await expect(card.getByRole("button", { name: "Lưu mẫu dựng" })).toBeDisabled();
  await chooseOption(page, card.getByLabel("Mẫu cho video mới của nhóm"), "Gợi ý của app");
  await card.getByRole("button", { name: "Lưu mẫu dựng" }).click();
  await expect(page.getByText("Đã lưu mẫu dựng của nhóm")).toBeVisible();

  const knowledge = await (await page.request.get("/api/knowledge")).json();
  const topic = knowledge.topics.find((item: { name: string }) => item.name === "Mẫu riêng");
  expect(topic.edit_template_default).toBe("app");
  // The api's CSRF guard wants the web's Origin, which the browser sends on its own.
  const made = await page.request.post("/api/videos", {
    data: { topic: "rau mầm", knowledge_topic_id: topic.id, mode: "manual", script: "Một\n\nHai" },
    headers: { Origin: new URL(page.url()).origin },
  });
  expect(made.ok()).toBe(true);
  const video = await made.json();
  expect(video.scenes.map((scene: { transition: string | null }) => scene.transition)).toEqual(["zoom", "slide"]);
  expect(video.edit_template).toEqual({ id: "app", name: "Gợi ý của app", source: "group" });
});

test("auto edit: the app's template on a video, undone, saved as a template and put on my new videos", async ({
  page,
}) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau mầm trồng tại nhà");
  await page.getByTestId("render-bar").getByRole("button", { name: "Xem trước" }).click();
  const studio = page.getByRole("dialog", { name: "Xem trước video" });
  await studio.getByRole("button", { name: "Tạm dừng" }).click();
  const timeline = studio.getByTestId("preview-timeline");

  // "Gợi ý của app": a sound on every scene; its closing line stays off, as the script's last scene is its own call
  // to action. Ctrl+Z takes it all back.
  await studio.getByRole("tab", { name: "Tự dựng" }).click();
  const panel = studio.getByTestId("auto-edit");
  await panel.getByRole("button", { name: "Áp mẫu Gợi ý của app" }).click();
  await expect(timeline.getByTestId("lane-sounds")).toHaveCount(6);
  await expect(timeline.getByTestId("lane-layers")).toHaveCount(0);

  // Its look, saved as the team's own template.
  await panel.getByLabel("Tên mẫu mới").fill("Vườn nhà");
  await panel.getByRole("button", { name: "Lưu" }).click();
  await expect(panel.getByTestId("template")).toHaveCount(2);
  await expect(panel.getByTestId("template").nth(1)).toContainText("Âm mỗi cảnh: Vút");

  await expect(studio.getByRole("button", { name: "Hoàn tác: áp mẫu Gợi ý của app (Ctrl+Z)" })).toBeVisible();
  await timeline.getByRole("slider", { name: "Đầu phát" }).focus();
  await page.keyboard.press("Control+z");
  await expect(timeline.getByTestId("lane-sounds")).toHaveCount(0);
  await expect(timeline.getByTestId("lane-layers")).toHaveCount(0);
  await page.keyboard.press("Escape");

  // Cài đặt › Mẫu dựng: "Vườn nhà" for every new video, put on as soon as its script is written.
  await page.goto("/settings/templates");
  await expect(page.getByTestId("template-card")).toHaveCount(2);
  await chooseOption(page, page.getByLabel("Mẫu cho video mới"), "Vườn nhà");
  await expect(page.getByTestId("template-card").nth(1)).toContainText("Video mới của tôi tự áp");
  // Its maker renames and deletes it; before deleting, they are told who puts it on their new videos.
  await page.getByRole("button", { name: "Xoá Vườn nhà" }).click();
  await expect(page.getByTestId("template-delete-usage")).toHaveText(
    "1 người đang chọn làm mẫu cho video mới. Xoá thì video mới của họ không còn tự áp mẫu này; video đã có giữ nguyên.",
  );
  await page.getByRole("tooltip").getByRole("button", { name: "Huỷ" }).click();
  await newVideoWithScript(page, "cải mầm cho người mới");
  await page.getByTestId("render-bar").getByRole("button", { name: "Xem trước" }).click();
  await expect(
    page.getByRole("dialog", { name: "Xem trước video" }).getByTestId("preview-timeline").getByTestId("lane-sounds"),
  ).toHaveCount(6);
});

test("AI suggested effects: chosen when making the video, the script comes with each scene's effects", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await page.goto("/videos");
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("rau mầm trồng tại nhà");
  await dialog.getByRole("checkbox", { name: "AI gợi ý hiệu ứng" }).check();
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await jobFinished(page);
  await uploadPhotos(page);

  // The (fake) AI gave every scene a transition, the first a "Ting" and the second a line of text.
  await page.getByTestId("render-bar").getByRole("button", { name: "Xem trước" }).click();
  const studio = page.getByRole("dialog", { name: "Xem trước video" });
  await studio.getByRole("button", { name: "Tạm dừng" }).click();
  const timeline = studio.getByTestId("preview-timeline");
  await expect(timeline.getByTestId("lane-sounds")).toHaveText(["Ting"]);
  await expect(timeline.getByTestId("lane-layers")).toHaveText(["Chữ: Dễ trồng"]);
  await timeline.getByRole("button", { name: "Xem Cảnh 1" }).click();
  await studio.getByRole("button", { name: "Tạm dừng" }).click();
  await expect(studio.getByTestId("scene-effects")).toContainText("Mở vòng tròn");
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

async function openPublish(page: Page) {
  // The button's name includes its icon's label.
  await page.getByRole("button", { name: "send Đăng bài", exact: true }).click();
}

/** A `datetime-local` value some hours from now: "Giờ đăng" is read as Vietnam time, not the browser's. */
function vietnamTimeIn(hours: number) {
  return new Date(Date.now() + (hours + 7) * 3600 * 1000).toISOString().slice(0, 16);
}

async function confirmPost(page: Page) {
  await page.getByRole("dialog", { name: "Đăng bài" }).getByRole("button", { name: "Đăng", exact: true }).click();
}

test("Đăng bài: a Facebook video's MP4 goes to TikTok and YouTube Shorts from one drawer", async ({ page }) => {
  test.setTimeout(240_000);
  await renderedVideo(page);
  await openPublish(page);
  const drawer = page.getByRole("dialog", { name: "Đăng bài" });
  // A Facebook video opens on Facebook; every platform is a tab of the same drawer.
  await expect(drawer.getByRole("tab", { name: "Facebook" })).toHaveAttribute("aria-selected", "true");
  await expect(drawer.getByLabel("Fanpage")).toBeVisible();

  // TikTok takes the Facebook video's own MP4; its Shopee products do not go in TikTok's cart.
  await drawer.getByRole("tab", { name: "TikTok" }).click();
  await expect(drawer.getByTestId("tiktok-from-facebook")).toContainText("Tạo bản TikTok");
  // Sending needs a connected TikTok account (none here); the form says where to connect one.
  await expect(drawer.getByTestId("tiktok-publish")).toContainText("Chưa có tài khoản TikTok nào đã kết nối");

  // YouTube Shorts is posted by hand and recorded with its link; the drawer has no "Đăng" button for it.
  await drawer.getByRole("tab", { name: "YouTube Shorts" }).click();
  await expect(drawer.getByRole("button", { name: "Đăng", exact: true })).toHaveCount(0);
  const youtube = drawer.getByTestId("manual-post-youtube");
  await youtube.getByLabel("Link bài YouTube Shorts").fill("https://evil.vn/shorts/AbCdEf12345");
  await youtube.getByRole("button", { name: "Ghi bài đã đăng" }).click();
  await expect(page.getByText("Link YouTube phải có dạng")).toBeVisible();
  await youtube.getByLabel("Link bài YouTube Shorts").fill("https://youtube.com/shorts/AbCdEf12345");
  await youtube.getByRole("button", { name: "Ghi bài đã đăng" }).click();
  await expect(youtube.getByTestId("manual-post")).toHaveCount(1);
  await expect(drawer.getByRole("tab", { name: "YouTube Shorts (1)" })).toBeVisible();
  await page.keyboard.press("Escape");

  // The video's posts on every platform are listed together, and its card says where else it is out.
  await expect(page.getByTestId("other-post")).toContainText("YouTube Shorts");
  await page.getByRole("menuitem", { name: "Video" }).click();
  const platforms = page.getByTestId("video-card").first().getByTestId("posted-platforms");
  await expect(platforms.locator('[data-platform="youtube"]')).toHaveAttribute("data-posted", "true");
  await expect(platforms.locator('[data-platform="instagram"]')).toHaveAttribute("data-posted", "false");
});

test("a posted video appears in Bài đăng and its calendar", async ({ page }) => {
  test.setTimeout(240_000);
  await renderedVideo(page);
  await openPublish(page);
  await confirmPost(page);
  await expect(page.getByTestId("publication-status")).toHaveText("Đã đăng lên Facebook", { timeout: 30_000 });

  await page.getByRole("menuitem", { name: "Bài đăng" }).click();
  await expect(page).toHaveURL(/\/posts$/);
  // A row per video, with its thumbnail and what its posts add up to; opening it lists each post.
  const groups = page.getByTestId("post-group");
  await expect(groups).toHaveCount(1);
  await expect(groups.locator("img")).toHaveAttribute("src", /\/thumbnail\.jpg/);
  await expect(groups).toContainText("1 bài đăng");
  await expect(groups.getByText("Đã đăng", { exact: true })).toBeVisible();
  await groups.getByRole("cell").last().click(); // the row, not the title's link
  const posts = page.getByTestId("post-rows");
  await expect(posts.getByRole("link", { name: "Xem Reel" })).toBeVisible();
  // On a phone the table scrolls inside its card instead of being cut off.
  await expect(posts.locator(".ant-table-content").first()).toHaveCSS("overflow-x", "auto");
  // Every post has the same action buttons; those that do not apply are greyed out.
  await expect(posts.getByRole("button", { name: "Thử lại" })).toBeDisabled();
  await expect(posts.getByRole("button", { name: "Kiểm tra" })).toBeEnabled();
  // Numbers come from the worker: a fresh reel has none until "Cập nhật view" asks for them.
  await expect(posts.getByText("Chưa có view", { exact: true })).toBeVisible();
  await posts.getByRole("button", { name: "Cập nhật view" }).click();
  await expect(posts.getByTestId("post-views")).toHaveText("1.200", { timeout: 30_000 });
  await expect(groups).toContainText("1.200");
  // The views stay on one line: the details sit in a tooltip.
  await expect(posts.getByText("3 share, 5 bình luận, 40 cảm xúc")).toHaveCount(0);
  await posts.getByTestId("post-views").hover();
  // The "Cập nhật view" button's tooltip may still be fading out, so pick the views tooltip by its text.
  const viewsTip = page.getByRole("tooltip").filter({ hasText: "3 share, 5 bình luận, 40 cảm xúc" });
  await expect(viewsTip).toBeVisible();
  await expect(viewsTip).toContainText("Xem TB 8,4 giây");
  // "Phân tích": every number, and the retention curve split by the posted MP4's scenes.
  await posts.getByRole("button", { name: "Phân tích bài đăng" }).click();
  const insights = page.getByTestId("post-insights");
  await expect(insights.getByTestId("insight-avg-watch")).toContainText("8,4 giây");
  await expect(insights.getByTestId("retention-chart")).toBeVisible();
  await expect(insights.getByTestId("scene-drop-off").getByRole("row")).toHaveCount(7); // header, title, 5 scenes
  await expect(insights.getByTestId("scene-drop-off").locator(".ant-table-content")).toHaveCSS("overflow-x", "auto");
  await expect(insights.getByText("mất nhiều nhất")).toHaveCount(1);
  await page.getByRole("dialog", { name: "Phân tích bài đăng" }).getByRole("button", { name: "Đóng" }).click(); // antd's vi_VN label for the X
  await chooseOption(page, page.getByLabel("Sắp xếp"), "Nhiều view nhất");
  await expect(groups).toHaveCount(1);
  // The KPIs: each figure on its own card, named plainly, with last week under it. The reel just went out, so
  // nothing has reached 48 hours: the cards say it is on its way instead of a bare "—".
  const kpis = page.getByTestId("kpi-card");
  await expect(kpis).toHaveCount(3);
  await expect(kpis.first()).toContainText("Bài đã đủ 48 giờ");
  await expect(kpis.first()).toContainText("Tuần trước:");
  await expect(kpis.first().getByTestId("kpi-note")).toContainText("Thêm 1 bài đang chờ, sớm nhất");
  await expect(kpis.nth(1).getByTestId("kpi-note")).toContainText("1 bài đang chờ đủ 48 giờ");
  // Its Page has no measured post yet, so the strip shows how far each Page is from a median to compare with.
  await expect(page.getByTestId("kpi-unlock")).toContainText("0/5 bài");
  // "Video thắng" was dropped: no winner card (three above), no winner filter.
  await expect(page.getByText("Chỉ video thắng")).toHaveCount(0);
  // The status tabs count the posts: a published reel is not among the scheduled or failed ones.
  const tabs = page.getByLabel("Lọc theo trạng thái");
  await expect(tabs.getByText("Đã đăng (1)")).toBeVisible();
  await expect(tabs.getByText("Thất bại (0)")).toBeVisible();
  await tabs.getByText("Đã hẹn lịch (0)").click();
  await expect(groups).toHaveCount(0);
  await expect(page.getByText("Không có bài đăng nào khớp")).toBeVisible();
  await tabs.getByText("Đang hoạt động (1)").click();
  await expect(groups).toHaveCount(1);
  // The search keeps posts whose title has the words.
  await page.getByLabel("Tìm theo tiêu đề").fill("không có tiêu đề này");
  await expect(groups).toHaveCount(0);
  await page.getByLabel("Tìm theo tiêu đề").fill("");
  await expect(groups).toHaveCount(1);

  // "Lịch" is a view of the same page; the sort chosen above stays in the address beside it.
  await page.getByLabel("Kiểu hiển thị").getByText("Lịch", { exact: true }).click();
  await expect(page).toHaveURL(/\/posts\?sort=views&view=calendar$/);
  await expect(page.getByRole("columnheader", { name: "T2" })).toBeVisible();
  // Choosing a day opens its posts in a drawer, each with a link to its video.
  // The week view is the default on a wide screen: a reel's cover sits in its hour.
  await page.getByTestId("week-post").first().click();
  const drawer = page.getByRole("dialog", { name: /^Bài đăng ngày / });
  await expect(drawer.getByTestId("calendar-drawer-post")).toHaveCount(1);
  await drawer.getByRole("link", { name: "Mở video" }).click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);

  // A phone shows the compact month with a dot; tapping the day opens its posts the same way.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/calendar"); // an old link lands on the calendar view
  await expect(page).toHaveURL(/\/posts\?view=calendar$/);
  await expect(page.locator(".ant-picker-cell-today [data-testid='calendar-dot']")).toBeVisible();
  await page.locator(".ant-picker-cell-today").click();
  await page
    .getByRole("dialog", { name: /^Bài đăng ngày / })
    .getByRole("link", { name: "Mở video" })
    .click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);
});

test("a posted video is a row of its Page's Nội dung tab, with columns to choose and a CSV file", async ({ page }) => {
  test.setTimeout(240_000);
  await renderedVideo(page);
  await openPublish(page);
  await confirmPost(page);
  await expect(page.getByTestId("publication-status")).toHaveText("Đã đăng lên Facebook", { timeout: 30_000 });

  await page.getByRole("menuitem", { name: "Quản lý Page" }).click();
  await page.getByRole("link", { name: "Trang Dưỡng Sinh" }).click();
  await page.getByRole("tab", { name: "Nội dung" }).click();
  const tab = page.getByRole("tabpanel", { name: "Nội dung" });
  const table = tab.getByTestId("content-table");
  const rows = table.locator("tbody tr.ant-table-row");
  await expect(rows).toHaveCount(1);
  await expect(tab).toContainText("1 bài app đăng trong 28 ngày");
  await expect(rows.getByText("Đã đăng", { exact: true })).toBeVisible();
  // A fresh reel has no numbers until the worker reads them; "Cập nhật view" in the row's menu asks for them.
  await expect(tab).toContainText("Cần ít nhất 5 bài có view 48 giờ để so với trung vị.");
  await rows.getByRole("button", { name: "Thao tác với bài" }).click();
  await expect(page.getByRole("menuitem", { name: "Mở reel trên Facebook" })).toBeVisible();
  await page.getByRole("menuitem", { name: "Cập nhật view" }).click();
  await expect(rows.getByRole("cell", { name: "1.200", exact: true })).toBeVisible({ timeout: 30_000 });
  for (const value of ["900", "40", "5", "3", "4", "8,4 giây"]) {
    await expect(rows.getByRole("cell", { name: value, exact: true })).toBeVisible();
  }

  // A number column sorts, most first.
  await table.getByRole("columnheader", { name: "Lượt xem" }).click();
  await expect(table.getByRole("columnheader", { name: "Lượt xem" })).toHaveAttribute("aria-sort", "descending");

  // "Cột" hides a column, and the choice stays in this browser.
  await tab.getByRole("button", { name: "Cột" }).click();
  await page.getByRole("checkbox", { name: "Tiếp cận" }).uncheck();
  await expect(table.getByRole("columnheader", { name: "Tiếp cận" })).toHaveCount(0);
  await page.reload();
  await page.getByRole("tab", { name: "Nội dung" }).click();
  await expect(table.getByRole("columnheader", { name: "Lượt xem" })).toBeVisible();
  await expect(table.getByRole("columnheader", { name: "Tiếp cận" })).toHaveCount(0);

  // The file has the shown columns of the shown rows, the title first and the reel's link last.
  const download = page.waitForEvent("download");
  await tab.getByRole("button", { name: "Xuất CSV" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^noi-dung-page-\d+-28-ngay\.csv$/);
  const text = (await readFile(await file.path(), "utf-8")).replace(/^﻿/, "");
  const [header, line] = text.split("\r\n");
  expect(header).toBe(
    "Tiêu đề,Lên lúc,Trạng thái,Lượt xem,Cảm xúc,Bình luận,Chia sẻ,Theo dõi,Xem TB,View 48 giờ,So với trung vị,Link reel",
  );
  expect(line).toContain(",Đã đăng,1200,40,5,3,4,8.4,,,https://www.facebook.com/reel/");

  // The title opens the video.
  await rows.getByRole("link").first().click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);
});

test("a rendered video waits in Sẵn sàng đăng until its Đăng there posts it", async ({ page }) => {
  test.setTimeout(240_000);
  await renderedVideo(page);
  const videoUrl = page.url();

  await page.getByRole("menuitem", { name: "Bài đăng" }).click();
  const ready = page.getByTestId("ready-to-post");
  await expect(ready.getByTestId("suggestion")).toHaveCount(1);
  await expect(ready).toContainText("Sẵn sàng đăng (1)");
  // Nothing did well yet, and with one Page only there is no other Page to make a variant for: the card says both.
  await expect(page.getByTestId("clone-suggestions")).toContainText(
    "Chưa có video nào cần nhân bản. Bản cho Page khác cần ít nhất 2 Fanpage đang dùng.",
  );

  // "Đăng" opens the video with its dialog open and the only Page picked; the address drops the request.
  await ready.getByRole("link", { name: "Đăng" }).click();
  const dialog = page.getByRole("dialog", { name: "Đăng bài" });
  await expect(dialog).toBeVisible();
  await expect(page).toHaveURL(videoUrl);
  await expect(dialog.getByLabel("Fanpage")).toBeVisible();
  await confirmPost(page);
  await expect(page.getByTestId("publication-status")).toHaveText("Đã đăng lên Facebook", { timeout: 30_000 });

  await page.getByRole("menuitem", { name: "Bài đăng" }).click();
  await expect(ready.getByTestId("suggestion")).toHaveCount(0);
  await expect(ready).toContainText("Không có video nào đang chờ đăng.");
});

test("a scheduled video appears in Bài đăng and its calendar without a link to the reel", async ({ page }) => {
  test.setTimeout(240_000);
  await renderedVideo(page);
  await openPublish(page);
  await page.getByLabel("Hẹn giờ").check();
  const typed = vietnamTimeIn(1);
  await page.getByLabel("Giờ đăng").fill(typed);
  await confirmPost(page);
  // The time comes back as it was typed, whatever the browser's time zone.
  const [date, time] = typed.split("T");
  const shown = `${date.split("-").reverse().join("/")} ${time}`;
  await expect(page.getByTestId("publication-status")).toContainText(`Đã hẹn đăng lúc ${shown}`, { timeout: 30_000 });

  await page.getByRole("menuitem", { name: "Bài đăng" }).click();
  await page.getByTestId("post-group").getByRole("cell").last().click();
  await expect(page.getByTestId("post-rows").getByRole("cell", { name: "Đã hẹn lịch" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Xem Reel" })).toHaveCount(0);
  await expect(page.getByTestId("post-rows").getByRole("button", { name: "Xem Reel" })).toBeDisabled();

  await page.getByLabel("Kiểu hiển thị").getByText("Lịch", { exact: true }).click();
  // The week view opens on this week; an hour ahead can already be next week, one "Sau" away.
  await expect(page.getByTestId("calendar-title")).toBeVisible();
  const reel = page.getByTestId("week-post");
  if ((await reel.count()) === 0) {
    await page.getByLabel("Sau").click();
  }
  await reel.first().click();
  await page
    .getByRole("dialog", { name: /^Bài đăng ngày / })
    .getByRole("link", { name: "Mở video" })
    .click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);
});

test("a scheduled post is cancelled, a posted one deleted, and both stay in Bài đăng with who did it", async ({
  page,
}) => {
  test.setTimeout(240_000);
  await renderedVideo(page);
  await openPublish(page);
  await page.getByLabel("Hẹn giờ").check();
  await page.getByLabel("Giờ đăng").fill(vietnamTimeIn(1));
  await confirmPost(page);
  await expect(page.getByTestId("publication-status")).toContainText("Đã hẹn đăng lúc", { timeout: 30_000 });

  // "Kiểm tra" reads the reel on Facebook; the fake still holds it for its time, so nothing changes.
  await page.getByRole("button", { name: "Kiểm tra" }).click();
  await expect(page.getByTestId("job-status")).toBeVisible();
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 30_000 });
  await expect(page.getByTestId("publication-status")).toContainText("Đã hẹn đăng lúc");

  await page.getByRole("button", { name: "Hủy đăng" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Hủy đăng" }).click();
  await expect(page.getByTestId("publication-status")).toHaveText("Đã hủy", { timeout: 30_000 });

  // Facebook no longer holds this MP4, so it can go out again.
  await openPublish(page);
  await confirmPost(page);
  await expect(page.getByTestId("publication-status")).toHaveText("Đã đăng lên Facebook", { timeout: 30_000 });

  await page.getByRole("menuitem", { name: "Bài đăng" }).click();
  // "Đang hoạt động" by default: the cancelled post is hidden, counted under its own tab.
  const groups = page.getByTestId("post-group");
  const tabs = page.getByLabel("Lọc theo trạng thái");
  await expect(groups).toHaveCount(1);
  await expect(groups).toContainText("1 bài đăng");
  await expect(tabs.getByText("Đã hủy/xóa (1)")).toBeVisible();
  await groups.getByRole("cell").last().click();
  const posts = page.getByTestId("post-rows");
  await posts.getByRole("button", { name: "Cập nhật view" }).click();
  await expect(posts.getByTestId("post-views")).toHaveText("1.200", { timeout: 30_000 });
  await posts.getByRole("button", { name: "Xóa", exact: true }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Xóa", exact: true }).click();
  // Deleted, it leaves the default list too, but stays one click away.
  await expect(groups).toHaveCount(0, { timeout: 30_000 });
  await expect(page.getByText("Không có bài nào đang hoạt động")).toBeVisible();
  await tabs.getByText("Đã hủy/xóa (2)").click();
  // Both posts belong to the same video: one row, opened to reach each post.
  await expect(groups).toHaveCount(1);
  await expect(groups).toContainText("2 bài đăng");
  await groups.getByRole("cell").last().click();
  await expect(posts.getByText("Đã xóa", { exact: true })).toBeVisible();
  // A deleted reel's last numbers are history: said as such, not bold like a live one's, and left out of the total.
  await expect(posts.getByTestId("post-views")).toHaveCount(0);
  await expect(posts.getByTestId("post-views-at-close")).toContainText("Lúc xóa: 1.200 view (đo lúc ");
  await expect(groups.getByRole("cell", { name: "1.200", exact: true })).toHaveCount(0);
  await expect(posts.getByText("Đã hủy", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Xem Reel" })).toHaveCount(0);
  // Who took each down and when, under its time; their action buttons are all greyed out.
  await expect(posts.getByText(new RegExp(`^Xóa: ${SEED.name}, `))).toBeVisible();
  await expect(posts.getByText(new RegExp(`^Hủy: ${SEED.name}, `))).toBeVisible();
  await expect(posts.getByRole("button", { name: "Kiểm tra" }).first()).toBeDisabled();

  await tabs.getByText("Tất cả (2)").click();
  await expect(groups).toHaveCount(1);
});

test("a posted reel takes an approved product and its link goes in the pinned comment", async ({ page, context }) => {
  test.setTimeout(240_000);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await renderedVideo(page);
  await openPublish(page);
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

  await page.getByRole("menuitem", { name: "Affiliate" }).click();
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

  // The filters: the reel now has a product to look at again, and none without a product.
  const linked = page.getByLabel("Lọc theo sản phẩm đã gắn");
  await expect(linked.getByText("Cần xem lại (1)")).toBeVisible();
  await linked.getByText("Chưa gắn (0)").click();
  await expect(page.getByText("Không có video nào khớp")).toBeVisible();
  await linked.getByText("Cần xem lại (1)").click();
  await expect(page.getByText("Đã bỏ duyệt: Trà sen")).toBeVisible();
  await chooseOption(page, page.getByLabel("Lọc theo nền tảng"), "TikTok");
  await expect(page.getByText("Không có video nào khớp")).toBeVisible();

  // By product: the videos it is attached to, and the count beside its name.
  await chooseOption(page, page.getByLabel("Lọc theo nền tảng"), "Facebook");
  await chooseOption(page, page.getByLabel("Lọc theo sản phẩm", { exact: true }), "Vừng đen rang (1 video)");
  await expect(page.getByText("Đã bỏ duyệt: Trà sen")).toBeVisible();
  await expect(linked.getByText("Tất cả (1)")).toBeVisible();
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
  await title.getByRole("button", { name: "Chọn từ kho" }).click();
  await page.getByRole("menuitem", { name: "Kho ảnh/video miễn phí" }).click();
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
  expect(body.source).toBe("pexels");
  expect(body.keyword).toBe("calcium rich food");
  expect(body.url).toMatch(/\/img\/\w+\.jpg$/);
  await expect(picker).toBeHidden();
  // The chosen photo is served by the app, not linked from Pexels.
  await expect(title.getByTestId("scene-preview")).toHaveAttribute("src", /^\/api\/scenes\/\d+\/preview\.jpg/);
  await expect(title.getByRole("button", { name: "Tìm ảnh (Pexels)" })).toBeVisible();

  // A content scene: a new keyword searches again, and the keyword that found the photo is kept first.
  const scenes = page.getByTestId("scene");
  const first = scenes.nth(0);
  await first.getByRole("button", { name: "Chọn từ kho" }).click();
  await page.getByRole("menuitem", { name: "Kho ảnh/video miễn phí" }).click();
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
  // The typed keyword was searched on Pexels, so it now leads the English list (not shown on the
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
  await third.getByRole("button", { name: "Chọn từ kho" }).click();
  await page.getByRole("menuitem", { name: "Kho ảnh/video miễn phí" }).click();
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
  await page.getByTestId("scene").first().getByRole("button", { name: "Chọn từ kho" }).click();
  await page.getByRole("menuitem", { name: "Kho ảnh/video miễn phí" }).click();
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

  // "Tìm trên Google" lists the scene's keywords; the one picked opens Google Ảnh, tall photos only.
  await page.context().route("https://www.google.com/**", (route) => route.fulfill({ body: "Google Ảnh" }));
  await scenes.nth(0).getByRole("button", { name: "Tìm trên Google" }).click();
  const second = page.locator(".ant-dropdown:visible").getByRole("menuitem").nth(1);
  const picked = (await second.innerText()).trim();
  const opened = page.waitForEvent("popup");
  await second.click();
  const google = new URL((await opened).url());
  expect(google.pathname).toBe("/search");
  expect(google.searchParams.get("q")).toBe(picked);
  expect(google.searchParams.get("udm")).toBe("2");
  expect(google.searchParams.get("tbs")).toBe("iar:t");

  // "Tìm trên TikTok" offers the Vietnamese keywords; the second one opens TikTok's video search. Google's menu
  // fades out first, or the same keyword would be found in both menus.
  await expect(page.locator(".ant-dropdown:visible")).toHaveCount(0);
  await page.context().route("https://www.tiktok.com/**", (route) => route.fulfill({ body: "TikTok" }));
  await scenes.nth(0).getByRole("button", { name: "Tìm trên TikTok" }).click();
  const tiktokOpened = page.waitForEvent("popup");
  await page.locator(".ant-dropdown:visible").getByRole("menuitem", { name: picked, exact: true }).click();
  const tiktok = new URL((await tiktokOpened).url());
  expect(tiktok.pathname).toBe("/search/video");
  expect(tiktok.searchParams.get("q")).toBe(picked);

  // "Dán ảnh/link" without clipboard permission opens a box; a copied thumbnail's data: address is uploaded.
  await scenes.nth(0).getByRole("button", { name: "Dán ảnh/link" }).click();
  let paste = page.getByRole("dialog", { name: /Dán ảnh hoặc video cho/ });
  await paste.getByLabel("Link ảnh").fill(PNG_DATA_URL);
  const uploaded = page.waitForRequest((request) => request.method() === "POST" && /\/image$/.test(request.url()));
  await paste.getByRole("button", { name: "Lấy về" }).click();
  await uploaded;
  await expect(scenes.nth(0).getByTestId("scene-preview")).toBeVisible();

  // A link is fetched by the api, which only reaches the public internet: this machine's address is refused.
  await scenes.nth(1).getByRole("button", { name: "Dán ảnh/link" }).click();
  paste = page.getByRole("dialog", { name: /Dán ảnh hoặc video cho/ });
  await paste.getByLabel("Link ảnh").fill("http://127.0.0.1:9/anh.jpg");
  await paste.getByRole("button", { name: "Lấy về" }).click();
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
  await scenes.nth(0).getByRole("button", { name: "Chọn từ kho" }).click();
  await page.getByRole("menuitem", { name: "Kho ảnh/video miễn phí" }).click();
  let picker = page.getByRole("dialog", { name: "Chọn từ kho ảnh" });
  await expect(picker.getByTestId("stock-hit")).toHaveCount(3);
  const taken = await picker.getByTestId("stock-hit").first().locator("img").getAttribute("src");
  await picker.getByTestId("stock-hit").first().click();
  await expect(picker).toBeHidden();

  await scenes.nth(1).getByRole("button", { name: "Chọn từ kho" }).click();

  await page.getByRole("menuitem", { name: "Kho ảnh/video miễn phí" }).click();
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
  await scene.getByRole("button", { name: "Chọn từ kho" }).click();
  await page.getByRole("menuitem", { name: "Kho ảnh/video miễn phí" }).click();
  const picker = page.getByRole("dialog", { name: "Chọn từ kho ảnh" });
  // Pexels is the default source: its three fake photos show first.
  await expect(picker.getByText(/ảnh từ Pexels cho/)).toBeVisible();
  await expect(picker.getByTestId("stock-hit")).toHaveCount(3);
  await picker.getByText("Pixabay", { exact: true }).click();
  await expect(picker.getByText(/ảnh từ Pixabay cho/)).toBeVisible();
  // The page polls the video every 2.5 s; a poll must not send the picker back to Pexels.
  const poll = (response: { url(): string; request(): { method(): string } }) =>
    /\/api\/videos\/\d+$/.test(response.url()) && response.request().method() === "GET";
  await page.waitForResponse(poll);
  await page.waitForResponse(poll);
  await expect(picker.getByText(/ảnh từ Pixabay cho/)).toBeVisible();
  await expect(picker.getByRole("radio", { name: "Pixabay" })).toBeChecked();
  await expect(picker.getByTestId("stock-hit")).toHaveCount(3);
  await picker.getByTestId("stock-hit").first().click();
  await expect(picker).toBeHidden();
  await expect(scene.getByTestId("scene-preview")).toBeVisible();

  // Reopen and take a photo from Openverse instead; the picker starts on Pexels again.
  await scene.getByRole("button", { name: "Chọn từ kho" }).click();
  await page.getByRole("menuitem", { name: "Kho ảnh/video miễn phí" }).click();
  await picker.getByText("Openverse", { exact: true }).click();
  await expect(picker.getByText(/ảnh từ Openverse cho/)).toBeVisible();
  await expect(picker.getByTestId("stock-hit")).toHaveCount(3);
  await picker.getByTestId("stock-hit").nth(1).click();
  await expect(picker).toBeHidden();
  await expect(scene.getByTestId("scene-preview")).toBeVisible();

  // "Tìm ảnh" searches Pexels until another source is picked from its arrow menu.
  const find = scene.getByRole("button", { name: "Tìm ảnh (Pexels)" });
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

test("a topic group puts Wikimedia first: the picker and “Tìm ảnh” follow it", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await page.goto("/knowledge");
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const group = page.locator('[data-topic="Sức khỏe"]');
  await group.getByRole("tab", { name: "Cài đặt nhóm" }).click();
  const card = group.getByTestId("stock-order-card");
  await expect(card).toContainText("Nhóm đang dùng thứ tự chung của app.");
  await expect(card.getByTestId("stock-order-item").first()).toContainText("Pexels");
  // Wikimedia is fourth in the app's order: three steps up.
  for (let step = 0; step < 3; step++) {
    await card.getByRole("button", { name: "Đưa Wikimedia Commons lên" }).click();
  }
  await card.getByRole("button", { name: "Lưu thứ tự" }).click();
  await expect(card).toContainText("Nhóm đang dùng thứ tự riêng.");
  await expect(card.getByTestId("stock-order-item").first()).toContainText("Wikimedia Commons");

  await newVideoWithScript(page, "canh chua cá");
  const scene = page.getByTestId("scene").first();
  await expect(scene.getByRole("button", { name: "Tìm ảnh (Wikimedia Commons)" })).toBeVisible();
  await scene.getByRole("button", { name: "Chọn từ kho" }).click();
  await page.getByRole("menuitem", { name: "Kho ảnh/video miễn phí" }).click();
  const picker = page.getByRole("dialog", { name: "Chọn từ kho ảnh" });
  await expect(picker.getByRole("radio", { name: "Wikimedia Commons" })).toBeChecked();
  await expect(picker.getByText(/ảnh từ Wikimedia Commons cho/)).toBeVisible();
  await expect(picker.getByTestId("stock-hit")).toHaveCount(3);
  await picker.getByTestId("stock-hit").first().click();
  await expect(picker).toBeHidden();
  // The fake's photos are public domain: no credit asked.
  await expect(scene.getByTestId("image-credit")).toHaveCount(0);

  // Back to the app's order.
  await page.goto("/knowledge");
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  await group.getByRole("tab", { name: "Cài đặt nhóm" }).click();
  await card.getByRole("button", { name: "Dùng thứ tự chung" }).click();
  await expect(card).toContainText("Nhóm đang dùng thứ tự chung của app.");
  await expect(card.getByTestId("stock-order-item").first()).toContainText("Pexels");
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
  // The radio's checked state, not .ant-segmented-item-selected: that class is left off while the thumb slides.
  await expect(choice.getByRole("radio", { name: "Cloudflare (miễn phí)" })).toBeChecked();
  await choice.getByLabel("Nguồn ảnh AI mặc định").getByText("Gemini (tốn phí)").click();
  await expect(choice.getByRole("radio", { name: "Gemini (tốn phí)" })).toBeChecked();
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
  await page.getByRole("menuitem", { name: "Nhật ký job" }).click();
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

  await page.getByRole("menuitem", { name: "Nhật ký job" }).click();
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
  // The topics are the groups of Kho kiến thức plus "chung"; the seed group is "Sức khỏe".
  await chooseOption(page, add.getByLabel("Chủ đề"), "Sức khỏe");
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
  await chooseOption(page, save.getByLabel("Chủ đề"), "chung");
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

  await page.getByRole("button", { name: "Thao tác khác với video" }).click();
  await page.getByRole("menuitem", { name: "Nhân bản" }).click();
  const dialog = page.getByRole("dialog", { name: "Nhân bản video" });
  await expect(dialog.getByRole("button", { name: "Tạo bản nhân bản" })).toBeDisabled();
  await dialog.getByLabel("Yêu cầu đổi").fill("đổi sang mốc 45 tuổi, tim mạch");
  await dialog.getByRole("button", { name: "Tạo bản nhân bản" }).click();

  await expect(page).not.toHaveURL(sourceUrl);
  await expect(page.getByTestId("clone-of")).toContainText("đổi sang mốc 45 tuổi, tim mạch");
  await jobFinished(page);
  await expect(page.getByTestId("music-name")).toBeVisible();

  await page.getByRole("menuitem", { name: "Nhật ký job" }).click();
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

test("Làm mờ vùng: a box drawn over a clip is saved, shown in the preview, then taken away", async ({ page }) => {
  test.setTimeout(240_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau ngót cho người lớn tuổi");
  const first = page.getByTestId("scene").first();
  await first.getByLabel("Tải ảnh/video lên cho cảnh", { exact: true }).setInputFiles(makeClip());
  await page
    .getByRole("dialog")
    .filter({ hasText: "Video sẽ thay ảnh của cảnh này?" })
    .getByRole("button", { name: "Đổi" })
    .click();
  await expect(first.getByTestId("scene-video")).toBeVisible();
  const preview = first.getByTestId("scene-preview");
  const plain = await preview.getAttribute("src");

  await first.getByRole("button", { name: "Làm mờ vùng" }).click();
  const dialog = page.getByRole("dialog", { name: "Làm mờ vùng trên video cảnh" });
  const frame = dialog.getByRole("img", { name: "Khung hình của cảnh" });
  await expect.poll(() => frame.evaluate((element: HTMLImageElement) => element.naturalWidth)).toBeGreaterThan(0);
  const area = (await dialog.getByTestId("image-edit-canvas").boundingBox())!;
  await page.mouse.move(area.x + area.width * 0.6, area.y + area.height * 0.05);
  await page.mouse.down();
  await page.mouse.move(area.x + area.width * 0.95, area.y + area.height * 0.12, { steps: 5 });
  await page.mouse.up();
  await expect(dialog.getByTestId("blur-box-count")).toHaveText("1 vùng sẽ được làm mờ");
  await dialog.getByRole("button", { name: "Lưu vùng mờ" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(first.getByTestId("clip-blurred")).toHaveText("Làm mờ 1 vùng trên video");
  await expect(preview).not.toHaveAttribute("src", plain ?? "");

  // "Bỏ làm mờ" takes the boxes away and the preview is the plain clip again.
  await first.getByRole("button", { name: "Làm mờ vùng" }).click();
  await dialog.getByRole("button", { name: "Bỏ làm mờ" }).click();
  await expect(first.getByTestId("clip-blurred")).toHaveCount(0);
  await expect(preview).toHaveAttribute("src", plain ?? "");
});

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

  // "Tốc độ clip": the scene keeps its seconds, and a clip too short at that speed warns instead of refusing.
  await title.getByRole("button", { name: "Cắt video" }).click();
  const speed = trim.getByRole("slider").last();
  await speed.focus();
  for (let step = 0; step < 4; step++) {
    await speed.press("ArrowRight");
  }
  await expect(trim.getByTestId("trim-speed")).toHaveText("2×");
  await expect(trim.getByTestId("trim-range")).toContainText("cảnh dài 2,3 giây");
  await expect(trim.getByTestId("trim-short")).toContainText("cảnh cần 5 giây clip");
  await trim.getByRole("button", { name: "Xem thử" }).click();
  await expect
    .poll(() => trim.getByTestId("trim-player").evaluate((video: HTMLVideoElement) => video.playbackRate))
    .toBe(2);
  await trim.getByRole("button", { name: "Áp dụng" }).click();
  await expect(trim).toHaveCount(0);
  await expect(title.getByLabel("Số giây")).toHaveValue("2.3");
  await expect(title.getByText("Ở tốc độ 2× video ngắn hơn cảnh, khung cuối sẽ đứng yên")).toBeVisible();

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
  await page.getByRole("menuitem", { name: "Cài đặt" }).click();
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
    "Tùy chỉnh (chuẩn OpenAI), fake-gpt-mini",
  );

  await page.getByRole("menuitem", { name: "Video" }).click();
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await expect(dialog.getByTestId("llm-line")).toContainText("Viết bằng: Tùy chỉnh (chuẩn OpenAI), fake-gpt-mini");
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("xương khớp sau 50 tuổi");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await jobFinished(page);
  await expect(page.getByTestId("script-by")).toHaveText("Kịch bản viết bởi Tùy chỉnh (chuẩn OpenAI) · fake-gpt-mini");

  await page.getByRole("menuitem", { name: "Nhật ký job" }).click();
  await expect(page.locator(".ant-table-tbody .ant-table-row").first()).toContainText(
    "Tùy chỉnh (chuẩn OpenAI) · fake-gpt-mini",
  );
});

test("video settings: a member's defaults reach their new video, which then changes its own", async ({ page }) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Cài đặt" }).click();
  await page.getByRole("tab", { name: "Thiết lập mặc định" }).click();
  await expect(page).toHaveURL(/\/settings\/defaults$/);
  // The page opens on the signed-in member's own defaults: none saved yet, so nothing to set back.
  await expect(page.getByRole("button", { name: "Về mặc định gốc" })).toHaveCount(0);
  // Read-only until "Chỉnh sửa"; "Huỷ" drops what was changed.
  await expect(page.getByRole("slider", { name: "Tốc độ đọc" })).toHaveAttribute("aria-disabled", "true");
  await page.getByRole("button", { name: "Chỉnh sửa" }).click();
  await page.getByLabel("Chuyển cảnh").getByText("Trượt").click();
  await page.getByRole("button", { name: "Huỷ" }).click();
  // The radio's checked state, not .ant-segmented-item-selected: that class is left off while the thumb slides,
  // and the thumb sliding back as "Huỷ" disables the control may never finish.
  await expect(page.getByLabel("Chuyển cảnh").getByRole("radio", { name: "Trượt" })).not.toBeChecked();
  await page.getByRole("button", { name: "Chỉnh sửa" }).click();
  await page.getByLabel("Chuyển cảnh").getByText("Cắt thẳng").click();
  // The reading speed slider: three steps up from 1 make 1.15.
  const speed = page.getByRole("slider", { name: "Tốc độ đọc" });
  for (const shown of ["1,05", "1,10", "1,15"]) {
    await expect(speed).not.toHaveAttribute("aria-disabled", "true");
    await speed.focus();
    await speed.press("ArrowRight");
    await expect(page.getByText(`Tốc độ đọc: ${shown}×`)).toBeVisible();
  }
  await expect(page.getByTestId("audio-settings")).toContainText("Adam (mặc định)");
  // The volume sliders follow the mouse while dragged (they used to stay put), and save when let go.
  const volume = page.getByRole("slider", { name: "Âm lượng giọng" });
  await expect(volume).not.toHaveAttribute("aria-disabled", "true");
  const handle = await volume.boundingBox();
  const rail = await page.getByTestId("audio-settings").locator(".ant-slider-rail").nth(1).boundingBox();
  if (!handle || !rail) throw new Error("the voice volume slider is not on the page");
  await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
  await page.mouse.down();
  await page.mouse.move(rail.x + rail.width / 2, handle.y + handle.height / 2, { steps: 10 });
  await expect(page.getByText("Âm lượng giọng: 50%")).toBeVisible();
  await page.mouse.up();
  await expect(volume).toHaveAttribute("aria-valuenow", "50");
  await page.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(page.getByText("Đã lưu mặc định của bạn")).toBeVisible();
  await expect(page.getByRole("button", { name: "Về mặc định gốc" })).toBeVisible();

  await page.getByRole("menuitem", { name: "Video" }).click();
  await newVideoWithScript(page, "xương khớp sau 50 tuổi");
  await page.getByRole("tab", { name: "Thiết lập" }).click();
  const motion = page.getByTestId("motion-settings");
  await expect(motion.getByLabel("Chuyển cảnh").getByRole("radio", { name: "Cắt thẳng" })).toBeChecked();
  await expect(page.getByText("Tốc độ đọc: 1,15×")).toBeVisible();
  await expect(page.getByRole("slider", { name: "Tốc độ đọc" })).toHaveAttribute("aria-valuenow", "1.15");

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
  await scene.getByRole("button", { name: "Chọn từ kho" }).click();
  await page.getByRole("menuitem", { name: "Kho ảnh/video miễn phí" }).click();
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

  await page.getByRole("menuitem", { name: "Cài đặt" }).click();
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
  // The team's settings say who changed them last, and their history never shows a key, only its last characters.
  const stockSection = page.locator("section").filter({ hasText: "Kho ảnh và video miễn phí" });
  await expect(stockSection.getByTestId("last-edit")).toContainText(`Sửa lần cuối bởi ${SEED.name}`);
  await page.getByRole("button", { name: "Lịch sử" }).click();
  const history = page.getByRole("dialog", { name: "Lịch sử: Nguồn tư liệu" });
  await expect(history.getByTestId("edit-history-entry")).toHaveCount(2);
  await expect(history).toContainText("Khoá (Pixabay): đã thêm khoá …-key");
  await expect(history).toContainText("Hiện trong hộp chọn (Pexels): Bật → Tắt");
  await expect(history).not.toContainText("fake-pixabay-key");
  await page.keyboard.press("Escape");
  // The ElevenLabs key for narration is pasted on the same page.
  const voiceKey = page.getByTestId("key-elevenlabs");
  await voiceKey.getByRole("button", { name: "Dán key mới" }).click();
  await voiceKey.getByLabel("API key ElevenLabs").fill("fake-elevenlabs-key");
  await voiceKey.getByRole("button", { name: "Lưu key" }).click();
  await expect(voiceKey.getByTestId("key-status")).toHaveText("Đã lưu, kết thúc bằng …-key");
  await expect(page.getByTestId("source-elevenlabs")).toContainText("Sẵn sàng");
  await page.goto(videoUrl);
  await page.getByTestId("scene").nth(1).getByRole("button", { name: "Chọn từ kho" }).click();
  await page.getByRole("menuitem", { name: "Kho ảnh/video miễn phí" }).click();
  await expect(picker.getByLabel("Nguồn ảnh")).not.toContainText("Pexels");
});

test("video defaults: only the member's own, saved and set back to the app's built-in ones", async ({ page }) => {
  await loginAsSeed(page);
  await page.goto("/settings/defaults");
  // A tab of the member's own: the menu says so, the page has no team level ("Của nhóm").
  await expect(page.getByRole("tab", { name: "Của tôi", exact: true })).toBeVisible();
  await expect(page.getByText("Của nhóm")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Về mặc định gốc" })).toHaveCount(0);
  await page.getByRole("button", { name: "Chỉnh sửa" }).click();
  await page.getByLabel("Chuyển cảnh").getByText("Cắt thẳng").click();
  await page.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(page.getByRole("button", { name: "Về mặc định gốc" })).toBeVisible();
  await expect(page.getByLabel("Chuyển cảnh").getByRole("radio", { name: "Cắt thẳng" })).toBeChecked();

  await page.getByRole("button", { name: "Về mặc định gốc" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Về mặc định gốc" }).click();
  await expect(page.getByRole("button", { name: "Về mặc định gốc" })).toHaveCount(0);
  await expect(page.getByLabel("Chuyển cảnh").getByRole("radio", { name: "Cắt thẳng" })).not.toBeChecked();
});

test("text settings from an api without the colour options still open, on Theo kiểu", async ({ page }) => {
  // An api older than the page (e.g. not restarted after an update) leaves the new colours out.
  await page.route(/\/api\/settings\/my-video-defaults$/, async (route) => {
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

test("text size: a smaller size on Thiết lập redraws the scenes' previews, the title on its own", async ({ page }) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau mầm trồng tại nhà");
  const scenePreview = page.getByTestId("scene").first().getByTestId("scene-preview");
  const titlePreview = page.getByTestId("title-scene").getByTestId("scene-preview");
  const [sceneBefore, titleBefore] = [await scenePreview.getAttribute("src"), await titlePreview.getAttribute("src")];
  await page.getByRole("tab", { name: "Thiết lập" }).click();
  const text = page.getByTestId("text-settings");
  await text.getByLabel("Cỡ chữ", { exact: true }).getByText("Nhỏ", { exact: true }).click();
  await expect(scenePreview).not.toHaveAttribute("src", sceneBefore ?? "");

  await text.getByText("Tiêu đề", { exact: true }).click();
  await text.getByLabel("Cỡ chữ tiêu đề", { exact: true }).getByText("Vừa", { exact: true }).click();
  await expect(titlePreview).not.toHaveAttribute("src", titleBefore ?? "");
});

test("text case: keeping the text as typed redraws the scenes' previews, and the title has its own", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau mầm trồng tại nhà");
  const scenePreview = page.getByTestId("scene").first().getByTestId("scene-preview");
  const titlePreview = page.getByTestId("title-scene").getByTestId("scene-preview");
  const [sceneBefore, titleBefore] = [await scenePreview.getAttribute("src"), await titlePreview.getAttribute("src")];
  await page.getByRole("tab", { name: "Thiết lập" }).click();
  const text = page.getByTestId("text-settings");
  const sceneCase = text.getByLabel("Dạng chữ", { exact: true });
  // Capitals, the original template, until a member chooses otherwise.
  await expect(sceneCase.getByRole("radio", { name: "Viết hoa toàn bộ" })).toBeChecked();
  await sceneCase.getByText("Giữ nguyên như đã nhập", { exact: true }).click();
  await expect(scenePreview).not.toHaveAttribute("src", sceneBefore ?? "");
  await expect(titlePreview).toHaveAttribute("src", titleBefore ?? "");

  await text.getByText("Tiêu đề", { exact: true }).click();
  const titleCase = text.getByLabel("Dạng chữ tiêu đề", { exact: true });
  await expect(titleCase.getByRole("radio", { name: "Viết hoa toàn bộ" })).toBeChecked();
  await titleCase.getByText("Giữ nguyên như đã nhập", { exact: true }).click();
  await expect(titlePreview).not.toHaveAttribute("src", titleBefore ?? "");
  // Saved with the video: a reload keeps both choices.
  await page.reload();
  await page.getByRole("tab", { name: "Thiết lập" }).click();
  await expect(
    text.getByLabel("Dạng chữ", { exact: true }).getByRole("radio", { name: "Giữ nguyên như đã nhập" }),
  ).toBeChecked();
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

test("video page: one poll at a time, none while the tab is hidden, and the menu prefetches no pages", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await newVideoWithScript(page, "rau xanh cho người lớn tuổi");
  const address = page.url();

  // The menu's pages are not rendered ahead: each prefetch is a server render through the slow web worker.
  const prefetched: string[] = [];
  page.on("request", (request) => {
    if (request.headers()["next-router-prefetch"]) {
      prefetched.push(request.url());
    }
  });
  await page.goto(address);
  await expect(page.getByTestId("title-scene")).toBeVisible();
  await page.waitForTimeout(3000);
  expect(prefetched).toEqual([]);

  // An answer slower than the 2.5 s refresh: the next poll waits for it instead of piling up.
  let polls = 0;
  let waiting = 0;
  let mostWaiting = 0;
  await page.route(/\/api\/videos\/\d+$/, async (route) => {
    if (route.request().method() !== "GET") {
      return route.continue();
    }
    polls += 1;
    waiting += 1;
    mostWaiting = Math.max(mostWaiting, waiting);
    await new Promise((resolve) => setTimeout(resolve, 4000));
    const response = await route.fetch();
    waiting -= 1;
    await route.fulfill({ response });
  });
  await page.waitForTimeout(12_000);
  expect(polls).toBeGreaterThanOrEqual(2);
  expect(mostWaiting).toBe(1);
  await page.unrouteAll({ behavior: "wait" });

  // A hidden tab stops asking; coming back asks at once.
  const setHidden = (hidden: boolean) =>
    page.evaluate((value) => {
      Object.defineProperty(document, "hidden", { configurable: true, get: () => value });
      document.dispatchEvent(new Event("visibilitychange"));
    }, hidden);
  await setHidden(true);
  await page.waitForTimeout(3000);
  let hiddenPolls = 0;
  page.on("request", (request) => {
    if (/\/api\/videos\/\d+$/.test(request.url()) && request.method() === "GET") {
      hiddenPolls += 1;
    }
  });
  await page.waitForTimeout(6000);
  expect(hiddenPolls).toBe(0);
  await Promise.all([
    page.waitForRequest((request) => /\/api\/videos\/\d+$/.test(request.url()) && request.method() === "GET", {
      timeout: 1500,
    }),
    setHidden(false),
  ]);
});

test("30-day plan: the plan prompt's history puts back the app's default", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Kho kiến thức" }).click();
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const health = page.locator('[data-topic="Sức khỏe"]');
  await health.getByRole("tab", { name: "Kế hoạch 30 ngày" }).click();
  const plan = health.getByTestId("plan-tab");
  await plan.getByRole("button", { name: "Prompt kế hoạch" }).click();
  const prompt = plan.getByLabel("Prompt kế hoạch");
  const original = await prompt.inputValue();
  await prompt.fill("Lên 30 ngày ý tưởng cho [Chủ đề nhóm]");
  await plan.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(page.getByText("Đã lưu prompt kế hoạch")).toBeVisible();
  await expect(plan.getByRole("button", { name: "Khôi phục mặc định" })).toHaveCount(0);

  await plan.getByRole("button", { name: "Lịch sử" }).click();
  const history = page.getByRole("dialog", { name: "Lịch sử: Prompt kế hoạch" });
  await expect(history.getByTestId("edit-history-entry")).toHaveCount(1);
  await history
    .getByTestId("edit-history-version")
    .filter({ hasText: "Bản mặc định của app" })
    .getByRole("button", { name: "Khôi phục bản này" })
    .click();
  await page.getByRole("dialog", { name: "Khôi phục bản này?" }).getByRole("button", { name: "Khôi phục" }).click();
  await expect(prompt).toHaveValue(original);
  await expect(history.getByTestId("edit-history-entry")).toHaveCount(2);
});

test("30-day plan: an idea added for today becomes a video, linked both ways", async ({ page }) => {
  await loginAsSeed(page);
  // The banner shows the plans of the member's own groups only: those their Pages post.
  await connectFacebook(page);
  await page.getByRole("menuitem", { name: "Quản lý Page" }).click();
  await page.getByRole("link", { name: "Trang Dưỡng Sinh" }).click();
  await page.getByRole("tab", { name: "Lịch đăng" }).click();
  const queue = page.getByRole("tabpanel", { name: "Lịch đăng" }).getByTestId("page-queue");
  await chooseOption(page, queue.getByLabel("Nhóm chủ đề của Trang Dưỡng Sinh"), "Sức khỏe");
  await expect(queue).toContainText("Theo giờ đăng của nhóm chủ đề (giờ Việt Nam).");
  await page.getByRole("menuitem", { name: "Kho kiến thức" }).click();
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const health = page.locator('[data-topic="Sức khỏe"]');
  await health.getByRole("tab", { name: "Kế hoạch 30 ngày" }).click();
  const plan = health.getByTestId("plan-tab");
  await expect(plan.getByLabel("Prompt kế hoạch")).toHaveCount(0);

  // Day 1 is today in Vietnam.
  await plan.getByRole("button", { name: "Thiết lập" }).click();
  await plan.getByPlaceholder("Chọn ngày 1").fill(vietnamDate(0));
  await page.keyboard.press("Enter");
  await plan.getByTestId("plan-settings").getByRole("button", { name: "Lưu" }).click();
  await expect(plan.getByTestId("plan-today")).toHaveText("Hôm nay là ngày 1/30");

  // A day opens in a drawer, where its ideas are added and worked on.
  await plan.getByRole("button", { name: "Chọn ngày 1", exact: true }).click();
  await page.getByRole("button", { name: "Thêm ý tưởng ngày 1", exact: true }).click();
  const add = page.getByRole("dialog", { name: "Thêm ý tưởng ngày 1" });
  await add.getByLabel("Chủ đề").fill("5 món sáng giúp ổn định huyết áp");
  await add.getByLabel("Nỗi đau người xem").fill("Sợ tai biến khi huyết áp lên xuống");
  await add.getByLabel("Góc hook").fill("Bỏ muối rồi vẫn chóng mặt?");
  await add.getByRole("button", { name: "Thêm" }).click();
  const idea = page.getByTestId("plan-day-panel").getByTestId("plan-idea");
  await expect(idea).toContainText("5 món sáng giúp ổn định huyết áp");
  await expect(idea).toContainText("Ý tưởng");

  await page.goto("/videos");
  await expect(page.getByTestId("plan-banner")).toHaveText(/ngày 1: hôm nay còn 1\/1 video/);
  await page.goto("/knowledge");
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  await health.getByRole("tab", { name: "Kế hoạch 30 ngày" }).click();
  await plan.getByRole("button", { name: "Chọn ngày 1", exact: true }).click();
  await idea.getByRole("button", { name: "Tạo video" }).click();

  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await expect(dialog.getByTestId("picked-idea")).toContainText("Theo kế hoạch, ngày 1");
  await expect(dialog.getByLabel("Chủ đề", { exact: true })).toHaveValue("5 món sáng giúp ổn định huyết áp");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page.getByTestId("plan-idea-card")).toContainText("Nỗi đau: Sợ tai biến khi huyết áp lên xuống");

  await page.goto("/videos");
  await expect(page.getByTestId("plan-banner")).toHaveText(/đã làm đủ 1 video hôm nay/);
  await page.goto("/knowledge");
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  await health.getByRole("tab", { name: "Kế hoạch 30 ngày" }).click();
  await plan.getByRole("button", { name: "Chọn ngày 1", exact: true }).click();
  await expect(idea).toContainText(/Đã tạo video|Đã viết kịch bản/);
  await expect(idea.getByRole("link", { name: /Mở video/ })).toBeVisible();
});

test("30-day plan: 2 ideas a day, and each idea is edited from its Sửa button", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Kho kiến thức" }).click();
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const health = page.locator('[data-topic="Sức khỏe"]');
  await health.getByRole("tab", { name: "Kế hoạch 30 ngày" }).click();
  const plan = health.getByTestId("plan-tab");

  // Pages post 1-2 videos a day: 2 is accepted and kept.
  await plan.getByRole("button", { name: "Thiết lập" }).click();
  const perDay = plan.getByLabel("Số ý tưởng mỗi ngày");
  await perDay.fill("2");
  await plan.getByTestId("plan-settings").getByRole("button", { name: "Lưu" }).click();
  await expect(plan.getByTestId("plan-settings")).toBeHidden();
  await page.reload();
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  await health.getByRole("tab", { name: "Kế hoạch 30 ngày" }).click();
  await plan.getByRole("button", { name: "Thiết lập" }).click();
  await expect(perDay).toHaveValue("2");
  await plan.getByTestId("plan-settings").getByRole("button", { name: "Huỷ" }).click();
  await plan.getByRole("button", { name: "Chọn ngày 5" }).click();

  // Two ideas on day 5, typed in; the day says nothing about being short.
  for (const topic of ["Uống nước ấm buổi sáng", "Đi bộ sau bữa tối"]) {
    await page.getByRole("button", { name: "Thêm ý tưởng ngày 5", exact: true }).click();
    const add = page.getByRole("dialog", { name: "Thêm ý tưởng ngày 5" });
    await add.getByLabel("Chủ đề").fill(topic);
    await add.getByRole("button", { name: "Thêm" }).click();
    await expect(add).toBeHidden();
  }
  const day = page.getByTestId("plan-day-panel");
  await expect(page.getByTestId("plan-day-title")).toContainText("Ngày 5");
  await expect(day.getByTestId("plan-idea")).toHaveCount(2);
  await expect(day).not.toContainText("nên có");

  // "Sửa" is on every card without hovering, in "Gọn" too.
  const second = day.getByTestId("plan-idea").filter({ hasText: "Đi bộ sau bữa tối" });
  await expect(day.getByRole("button", { name: "Sửa" })).toHaveCount(2);
  const filters = page.getByTestId("plan-filters");
  await filters.getByText("Gọn", { exact: true }).click();
  await expect(day.getByRole("button", { name: "Sửa" })).toHaveCount(2);
  await filters.getByText("Đầy đủ", { exact: true }).click();
  // The text itself is not editable any more: one way to edit.
  await expect(day.getByRole("button", { name: /Sửa chủ đề/ })).toHaveCount(0);

  // "Huỷ" leaves the idea as it was and asks nothing of the server.
  let patches = 0;
  page.on("request", (request) => {
    if (/\/api\/plans\/items\/\d+$/.test(request.url()) && request.method() === "PATCH") patches += 1;
  });
  await second.getByRole("button", { name: "Sửa" }).click();
  const edit = page.getByRole("dialog", { name: "Sửa ý tưởng" });
  await expect(edit.getByLabel("Chủ đề")).toHaveValue("Đi bộ sau bữa tối");
  await edit.getByLabel("Chủ đề").fill("Không lưu");
  await edit.getByRole("button", { name: "Huỷ" }).click();
  // Typing is not dropped without asking.
  await page
    .locator(".ant-modal-confirm")
    .filter({ hasText: "Bỏ các thay đổi chưa lưu?" })
    .getByRole("button", { name: "Bỏ thay đổi" })
    .click();
  await expect(edit).toBeHidden();
  await expect(second).toContainText("Đi bộ sau bữa tối");
  expect(patches).toBe(0);

  // An error from the server shows in the form, which stays open.
  await second.getByRole("button", { name: "Sửa" }).click();
  await expect(edit.getByLabel("Chủ đề")).toHaveValue("Đi bộ sau bữa tối");
  await edit.getByLabel("Chủ đề").fill("Uống nước ấm buổi sáng");
  await edit.getByRole("button", { name: "Lưu" }).click();
  await expect(edit.getByRole("alert")).toContainText("Kế hoạch đã có chủ đề này");
  await expect(edit).toBeVisible();

  // "Lưu" saves the four fields in one request.
  await edit.getByLabel("Chủ đề").fill("Đi bộ 15 phút sau bữa tối");
  await edit.getByLabel("Nhóm nỗi đau").fill("Tiêu hoá");
  await edit.getByLabel("Nỗi đau người xem").fill("Đầy bụng khó ngủ");
  await edit.getByLabel("Góc hook").fill("Nằm ngay sau ăn là sai");
  patches = 0;
  await edit.getByRole("button", { name: "Lưu" }).click();
  await expect(edit).toBeHidden();
  expect(patches).toBe(1);
  const edited = day.getByTestId("plan-idea").filter({ hasText: "Đi bộ 15 phút sau bữa tối" });
  await expect(edited).toContainText("Tiêu hoá");
  await expect(edited).toContainText("Đầy bụng khó ngủ");
  await expect(edited).toContainText("Nằm ngay sau ăn là sai");

  // Closing the drawer keeps the page where it was; the day's chips show the edit.
  const scrolled = await page.evaluate(() => window.scrollY);
  // Scoped to the day's drawer: the plan's other drawers ("Thêm ý tưởng vào Backlog") have a "Đóng" too.
  await page.getByTestId("plan-day-drawer").getByRole("button", { name: "Đóng" }).click();
  await expect(day).toBeHidden();
  expect(await page.evaluate(() => window.scrollY)).toBe(scrolled);
  await expect(
    plan.getByTestId("plan-day-5").getByTestId("plan-chip").filter({ hasText: "Đi bộ 15 phút" }),
  ).toHaveCount(1);
});

/** "dd/mm/yyyy" of today in Vietnam, moved by `days`; with the short weekday the calendar shows ("CN 08/11"). */
function vietnamDate(days: number): string {
  return vietnamDay(days).full;
}

function vietnamDay(days: number): { full: string; short: string; cell: string; long: string } {
  const [year, month, day] = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" })
    .format(new Date())
    .split("-")
    .map(Number);
  const date = new Date(Date.UTC(year, month - 1, day + days));
  const pad = (n: number) => String(n).padStart(2, "0");
  const short = `${pad(date.getUTCDate())}/${pad(date.getUTCMonth() + 1)}`;
  const weekday = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"][date.getUTCDay()];
  const long = ["Chủ nhật", "Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy"][date.getUTCDay()];
  return { full: `${short}/${date.getUTCFullYear()}`, short, cell: `${weekday} ${short}`, long: `${long}, ${short}` };
}

test("30-day plan: weeks of days, today's ideas on top, and settings saved together", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Kho kiến thức" }).click();
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const health = page.locator('[data-topic="Sức khỏe"]');
  await health.getByRole("tab", { name: "Kế hoạch 30 ngày" }).click();
  const plan = health.getByTestId("plan-tab");
  await expect(plan.getByTestId("plan-strip")).toHaveCount(0);
  await expect(plan.getByTestId("plan-legend")).toContainText("Đã lên lịch");

  // Thiết lập: "Huỷ" drops what was changed, "Lưu" sends the changed fields once.
  let patches = 0;
  page.on("request", (request) => {
    if (/\/api\/plans\/\d+$/.test(request.url()) && request.method() === "PATCH") patches += 1;
  });
  const settings = plan.getByTestId("plan-settings");
  await plan.getByRole("button", { name: "Thiết lập" }).click();
  const perDay = settings.getByLabel("Số ý tưởng mỗi ngày");
  const before = await perDay.inputValue();
  await perDay.fill(before === "3" ? "4" : "3");
  await settings.getByRole("button", { name: "Huỷ" }).click();
  await expect(settings).toBeHidden();
  await plan.getByRole("button", { name: "Thiết lập" }).click();
  await expect(perDay).toHaveValue(before);
  expect(patches).toBe(0);

  // Today is day 7.
  await settings.getByPlaceholder("Chọn ngày 1").fill(vietnamDate(-6));
  await page.keyboard.press("Enter");
  await perDay.fill("3");
  await settings.getByLabel("Mục tiêu video").fill("12");
  await settings.getByRole("button", { name: "Lưu" }).click();
  await expect(settings).toBeHidden();
  expect(patches).toBe(1);
  await expect(plan.getByTestId("plan-verdict")).toContainText("/12 video");

  // The calendar: day 7 is today, with its weekday and date; a day opens in a drawer only when picked.
  const seventh = plan.getByTestId("plan-day-7");
  await expect(seventh).toContainText(vietnamDay(0).cell);
  await expect(seventh).toContainText("Hôm nay");
  const dayPanel = page.getByTestId("plan-day-panel");
  const dayTitle = page.getByTestId("plan-day-title");
  await expect(dayPanel).toHaveCount(0);
  await plan.getByRole("button", { name: "Chọn ngày 7" }).click();
  await expect(dayTitle).toHaveText(`Ngày 7 — ${vietnamDay(0).long}`);
  await page.getByTestId("plan-day-drawer").getByRole("button", { name: "Đóng" }).click();
  await expect(dayPanel).toBeHidden();
  await expect(plan.getByTestId("plan-week-2")).toContainText(
    `Tuần 2, ${vietnamDay(1).short} – ${vietnamDay(7).short}`,
  );

  // An empty day offers "+ Thêm ý"; the idea lands on that day, which is then shown.
  await plan.getByRole("button", { name: "Thêm ý ngày 12" }).click();
  const add = page.getByRole("dialog", { name: "Thêm ý tưởng ngày 12" });
  await add.getByLabel("Chủ đề").fill("Ngủ trưa 20 phút cho tim khoẻ");
  await add.getByRole("button", { name: "Thêm" }).click();
  await expect(add).toBeHidden();
  await expect(plan.getByTestId("plan-day-12").getByTestId("plan-chip")).toHaveText(/Ngủ trưa 20 phút/);
  await expect(dayTitle).toHaveText(`Ngày 12 — ${vietnamDay(5).long}`);
  await expect(dayPanel.getByTestId("plan-idea")).toHaveCount(1);
  await expect(plan.getByTestId("plan-week-2")).toContainText("1 ý tưởng, 0 đã làm, 0 đã lên lịch");

  // Another day opens in the drawer in its place.
  await page.getByTestId("plan-day-drawer").getByRole("button", { name: "Đóng" }).click();
  await plan.getByRole("button", { name: "Chọn ngày 13" }).click();
  await expect(dayTitle).toContainText("Ngày 13");
  await expect(dayPanel).toContainText("Chưa có ý tưởng");
  await page.getByTestId("plan-day-drawer").getByRole("button", { name: "Đóng" }).click();

  // Dragging a chip onto another day moves the idea there.
  await plan.getByTestId("plan-day-12").getByTestId("plan-chip").dragTo(plan.getByTestId("plan-day-13"));
  await expect(plan.getByTestId("plan-day-13").getByTestId("plan-chip")).toHaveText(/Ngủ trưa 20 phút/);
  await expect(plan.getByTestId("plan-day-12").getByTestId("plan-chip")).toHaveCount(0);

  // Today's strip lists today's ideas with their next step and "Sửa".
  const strip = plan.getByTestId("plan-today-strip");
  await expect(plan.getByTestId("plan-today")).toHaveText("Hôm nay là ngày 7/30");
  await plan.getByRole("button", { name: "Chọn ngày 7" }).click();
  await page.getByRole("button", { name: "Thêm ý tưởng ngày 7", exact: true }).click();
  const addToday = page.getByRole("dialog", { name: "Thêm ý tưởng ngày 7" });
  await addToday.getByLabel("Chủ đề").fill("Uống trà gừng sau bữa sáng");
  await addToday.getByRole("button", { name: "Thêm" }).click();
  const todayIdea = strip.getByTestId("plan-today-idea").filter({ hasText: "Uống trà gừng sau bữa sáng" });
  await expect(todayIdea).toContainText("Ý tưởng");
  await expect(todayIdea.getByRole("button", { name: "Tạo video" })).toBeVisible();
  await expect(todayIdea.getByRole("button", { name: "Sửa" })).toBeVisible();
  await expect(plan.getByTestId("plan-summary")).toHaveText(/^Đã làm \d+\/\d+, đã lên lịch \d+, ngày còn trống \d+$/);

  // The filters apply to the day in the drawer, not to the calendar, and stay when it is closed.
  await page.getByTestId("plan-filters").getByLabel("Tìm ý tưởng").fill("không có ý nào như thế");
  await expect(dayPanel).toContainText("Không có ý tưởng khớp");
  await expect(plan.getByTestId("plan-day-13").getByTestId("plan-chip")).toHaveCount(1);
  await page.getByTestId("plan-day-drawer").getByRole("button", { name: "Đóng" }).click();
  await plan.getByRole("button", { name: "Chọn ngày 13" }).click();
  await expect(page.getByTestId("plan-filters").getByLabel("Tìm ý tưởng")).toHaveValue("không có ý nào như thế");
  await expect(dayPanel).toContainText("Không có ý tưởng khớp");

  // A press on the mask outside the drawer closes it too, and keeps the scroll, the filters and the chosen day.
  const scrolled = await page.evaluate(() => window.scrollY);
  await page.locator(".ant-drawer-mask").click({ position: { x: 20, y: 300 } });
  await expect(dayPanel).toBeHidden();
  expect(await page.evaluate(() => window.scrollY)).toBe(scrolled);
  await plan.getByRole("button", { name: "Chọn ngày 13" }).click();
  await expect(dayTitle).toContainText("Ngày 13");
  await expect(page.getByTestId("plan-filters").getByLabel("Tìm ý tưởng")).toHaveValue("không có ý nào như thế");
  // A press inside it, or on one of its pop-ups, leaves it open.
  await page.getByTestId("plan-filters").getByLabel("Lọc trạng thái").click();
  await page.locator(".ant-select-dropdown").getByText("Ý tưởng", { exact: true }).click();
  await expect(dayPanel).toBeVisible();
});

test("knowledge topics: a group's maker turns off Cho cả đội sửa, and a teammate only reads and uses it", async ({
  page,
  browser,
}) => {
  await loginAsSeed(page);
  await addUser(page, "binh@doi.vn", "Trần Bình", "mat-khau-tam-1");
  await page.getByRole("menuitem", { name: "Kho kiến thức" }).click();
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const health = page.locator('[data-topic="Sức khỏe"]');
  // Nobody is known to have made "Sức khỏe": it is claimed first, as a Page is.
  await health.getByRole("button", { name: "Nhận nhóm" }).click();
  const teamEdit = health.getByRole("switch", { name: "Cho cả đội sửa" });
  await expect(teamEdit).toBeChecked();
  await teamEdit.click();
  await expect(teamEdit).not.toBeChecked();

  const binh = await (await browser.newContext({ baseURL: "http://localhost:3100", locale: "vi-VN" })).newPage();
  await login(binh, "binh@doi.vn", "mat-khau-tam-1");
  await binh.getByLabel("Mật khẩu mới", { exact: true }).fill("binh-moi-1234");
  await binh.getByLabel("Nhập lại mật khẩu mới").fill("binh-moi-1234");
  await binh.getByRole("button", { name: "Lưu mật khẩu mới" }).click();
  await expect(binh).toHaveURL(/\/videos$/);
  await binh.goto("/knowledge");
  await binh.getByRole("button", { name: /Sức khỏe/ }).click();
  const theirs = binh.locator('[data-topic="Sức khỏe"]');
  await expect(theirs.getByTestId("group-locked")).toContainText(`chỉ ${SEED.name} sửa được nhóm này`);
  await expect(theirs.getByRole("switch", { name: "Cho cả đội sửa" })).toHaveCount(0);
  await expect(theirs.getByRole("button", { name: "Đổi tên" })).toHaveCount(0);
  // Its videos are still made by anyone; its prompts are read, not edited.
  await expect(theirs.getByRole("button", { name: "Tạo video" })).toBeEnabled();
  await theirs.getByRole("tab", { name: "Prompt", exact: true }).click();
  await expect(theirs.getByLabel("Prompt viết kịch bản", { exact: true })).toBeDisabled();
  await theirs.getByRole("tab", { name: "Cài đặt nhóm" }).click();
  await expect(theirs.getByLabel("Từ cấm", { exact: true })).toBeDisabled();

  // Turned back on, the teammate edits again.
  await teamEdit.click();
  await expect(teamEdit).toBeChecked();
  await binh.reload();
  await binh.getByRole("button", { name: /Sức khỏe/ }).click();
  await expect(theirs.getByTestId("group-locked")).toHaveCount(0);
  await expect(theirs.getByRole("button", { name: "Đổi tên" })).toBeVisible();
});
