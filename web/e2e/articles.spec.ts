import { expect, test } from "@playwright/test";
import { addUser, connectFacebook, login, loginAsSeed, resetDatabase } from "./helpers";

test.beforeEach(() => resetDatabase());

test("Bài viết: create a draft, let the AI write the caption, make a text card and drop it", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Bài viết" }).click();
  await expect(page).toHaveURL(/\/articles$/);
  await expect(page.getByText("Chưa có bài viết nào")).toBeVisible();

  await page.getByRole("button", { name: "Tạo bài viết" }).click();
  const drawer = page.getByRole("dialog", { name: "Tạo bài viết" });
  await drawer.getByLabel("Chủ đề của bài").fill("uống nước ấm buổi sáng");
  await drawer.getByRole("button", { name: "Tạo bài" }).click();
  await expect(page).toHaveURL(/\/articles\/\d+$/);
  // A new draft has no caption, which is what still blocks; no picture is fine.
  await expect(page.getByText("Chưa có caption", { exact: true })).toBeVisible();
  await expect(page.getByText("Chưa có ảnh: bài sẽ đăng dạng chỉ chữ.")).toBeVisible();

  await page.getByRole("button", { name: "AI viết" }).click();
  const caption = page.getByLabel("Caption");
  // The worker starts a process per job, as for a video's script.
  await expect(caption).toHaveValue(/^Bạn có đang hiểu sai về uống nước ấm buổi sáng\?/, { timeout: 90_000 });
  // The AI's own reminder, in the post's voice, closes the body; no fixed sentence is added, and the question ends it.
  await expect(caption).toHaveValue(
    /Ai đang có bệnh nền thì hỏi bác sĩ trước khi đổi thói quen nhé\.\n\nBạn đã thử cách này chưa\?$/,
  );
  await expect(caption).not.toHaveValue(/Tham khảo, không thay thế tư vấn bác sĩ/);
  await expect(page.getByLabel("Bình luận ghim")).toHaveValue("Bạn làm cách này lâu chưa, kể mình nghe với!");
  await expect(page.getByLabel("Gợi ý sản phẩm")).toHaveValue("bình giữ nhiệt");
  await expect(page.getByTestId("article-preview-comment")).toContainText("Bạn làm cách này lâu chưa");
  await expect(page.getByText("Chưa có caption", { exact: true })).toBeHidden();
  const preview = page.getByTestId("article-preview");
  await expect(preview).toContainText("#suckhoe #meovat");

  // A link typed into the caption is flagged: product links only go in the pinned comment.
  await caption.fill(`Mua ở shope.ee/abc\n\nTham khảo, không thay thế tư vấn bác sĩ.`);
  await caption.blur();
  await expect(page.getByText("Caption có link: link sản phẩm chỉ để ở bình luận ghim")).toBeVisible();
  await caption.fill(`Ngủ đủ giấc quan trọng hơn bạn nghĩ\n\nTham khảo, không thay thế tư vấn bác sĩ.`);
  await caption.blur();
  await expect(page.getByText("Caption có link: link sản phẩm chỉ để ở bình luận ghim")).toBeHidden();

  const photos = page.getByTestId("article-images");
  await photos.getByRole("button", { name: "Thẻ chữ" }).click();
  await page.getByRole("menuitem", { name: "Thẻ chữ Xanh lá" }).click();
  await expect(photos.getByRole("button", { name: "Ảnh 1", exact: true })).toBeVisible();
  await expect(photos.getByText("Ảnh bài viết (1/10)")).toBeVisible();
  // The chosen photo is shown as the api draws it for the Page (no Page here, so no logo).
  await expect(photos.getByRole("img", { name: "Ảnh 1 có logo" })).toBeVisible();
  await expect(preview.getByRole("img", { name: "Ảnh của bài" })).toBeVisible();
  await photos.getByRole("button", { name: "Bỏ ảnh" }).click();
  await expect(page.getByText("Chưa có ảnh: bài sẽ đăng dạng chỉ chữ.")).toBeVisible();

  await page.getByRole("link", { name: "Về danh sách bài viết" }).click();
  await expect(page.getByRole("link", { name: "Ngủ đủ giấc quan trọng hơn bạn nghĩ" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Kiến thức ngắn" })).toBeVisible();
});

test("Bài viết: make a composite photo (text band over the photo), open it again and change it", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Bài viết" }).click();
  await page.getByRole("button", { name: "Tạo bài viết" }).click();
  const drawer = page.getByRole("dialog", { name: "Tạo bài viết" });
  await drawer.getByLabel("Chủ đề của bài").fill("cải bó xôi");
  await drawer.getByRole("button", { name: "Tạo bài" }).click();
  await expect(page).toHaveURL(/\/articles\/\d+$/);
  const caption = page.getByLabel("Caption");
  await caption.fill("Hay mệt mỏi, hoa mắt?\n\nThêm cải bó xôi vào bữa ăn mỗi ngày.");
  await caption.blur();

  const photos = page.getByTestId("article-images");
  // Without a photo there is nothing to put the text over.
  await expect(photos.getByRole("button", { name: "Ảnh ghép chữ + ảnh" })).toBeDisabled();
  // A text card stands in for the dish photo: the composite takes it as its source.
  await photos.getByRole("button", { name: "Thẻ chữ" }).click();
  await page.getByRole("menuitem", { name: "Thẻ chữ Xanh lá" }).click();
  await expect(photos.getByText("Ảnh bài viết (1/10)")).toBeVisible();

  await photos.getByRole("button", { name: "Ảnh ghép chữ + ảnh" }).click();
  const maker = page.getByRole("dialog", { name: "Ảnh ghép chữ + ảnh" });
  // Empty lines: the api splits the caption's first line, and the preview is drawn by it.
  await expect(maker.getByRole("img", { name: "Xem trước ảnh ghép" })).toBeVisible();
  await maker.getByLabel("Dòng tiêu đề 1").fill("Hay mệt mỏi, hoa mắt?");
  await maker.getByLabel("Dòng tiêu đề 2").fill("Thêm cải bó xôi");
  await maker.getByLabel("Nhãn series").fill("ngày 5 · thực phẩm");
  await expect(maker.getByText(/Nền mờ · chữ \d+px/)).toBeVisible(); // a portrait photo is kept whole on a blur
  await maker.getByRole("button", { name: "Tạo ảnh ghép" }).click();

  // The text card and its photo went; the composite is the only photo, with its own label.
  await expect(photos.getByText("Ảnh bài viết (1/10)")).toBeVisible();
  await expect(photos.getByText("Ảnh ghép", { exact: true })).toBeVisible();
  await photos.getByRole("button", { name: "Sửa ảnh ghép" }).click();
  const editor = page.getByRole("dialog", { name: "Sửa ảnh ghép" });
  await expect(editor.getByLabel("Dòng tiêu đề 2")).toHaveValue("Thêm cải bó xôi");
  await expect(editor.getByLabel("Nhãn series")).toHaveValue("NGÀY 5 · THỰC PHẨM");
  await editor.getByLabel("Dòng tiêu đề 3").fill("vào bữa ăn mỗi ngày");
  await editor.getByRole("button", { name: "Lưu ảnh ghép" }).click();
  await expect(editor).toBeHidden();
  await photos.getByRole("button", { name: "Sửa ảnh ghép" }).click();
  await expect(page.getByRole("dialog", { name: "Sửa ảnh ghép" }).getByLabel("Dòng tiêu đề 3")).toHaveValue(
    "vào bữa ăn mỗi ngày",
  );
});

test("Bài viết: post a text article to a Page, read its numbers, take it down, and make a reel from it", async ({
  page,
}) => {
  // Posting alone may take up to 60 s on a slow runner, then the numbers, the second try and taking it down: the
  // default 60 s for the whole test ran out on CI (2026-11-08) while each step was still in its own time.
  test.setTimeout(180_000);
  await loginAsSeed(page);
  await connectFacebook(page);
  await page.getByRole("menuitem", { name: "Bài viết" }).click();
  await page.getByRole("button", { name: "Tạo bài viết" }).click();
  const drawer = page.getByRole("dialog", { name: "Tạo bài viết" });
  await drawer.getByLabel("Chủ đề của bài").fill("ngâm chân nước gừng");
  await drawer.getByRole("button", { name: "Tạo bài" }).click();
  await expect(page).toHaveURL(/\/articles\/\d+$/);
  const caption = page.getByLabel("Caption");
  await caption.fill("Ngâm chân nước gừng trước khi ngủ\n\nTham khảo, không thay thế tư vấn bác sĩ.");
  await caption.blur();
  await expect(page.getByText("Chưa có caption", { exact: true })).toBeHidden();

  const openPublish = page.getByRole("button", { name: /^send Đăng$/ });
  await openPublish.click();
  const publish = page.getByRole("dialog", { name: "Đăng bài viết" });
  const publishNow = publish.getByRole("button", { name: "Đăng", exact: true });
  // The one Page in use is already picked.
  await publishNow.click();
  await expect(publish).toBeHidden();
  await expect(page.getByTestId("article-status")).toHaveText("Đã đăng", { timeout: 60_000 });
  const post = page.getByTestId("article-post");
  await expect(post.getByText("Trang Dưỡng Sinh")).toBeVisible();
  await expect(post.getByRole("link", { name: "Xem bài" })).toBeVisible();
  await expect(post.getByText("chưa đo 48h")).toBeVisible();

  await post.getByRole("button", { name: "Cập nhật số" }).click();
  await expect(post.getByText(/Mới nhất .*30 cảm xúc, 6 bình luận, 2 chia sẻ, reach 400/)).toBeVisible({
    timeout: 30_000,
  });

  // The same caption cannot go on the same Page twice.
  await openPublish.click();
  const [refusal] = await Promise.all([
    page.waitForResponse(
      (response) => response.request().method() === "POST" && /\/api\/articles\/\d+\/publish$/.test(response.url()),
    ),
    publishNow.click(),
  ]);
  expect(refusal.status()).toBe(409);
  expect((await refusal.json()).code).toBe("already_on_page");
  await expect(page.getByText("Nội dung này đã đăng hoặc đã hẹn trên Page này, không đăng lại được")).toBeVisible();
  await publish.getByRole("button", { name: "Huỷ" }).click();
  await expect(publish).toBeHidden();

  await post.getByRole("button", { name: "Gỡ bài" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Gỡ bài" }).click();
  await expect(post.getByText("Đã gỡ")).toBeVisible({ timeout: 60_000 });

  await page.getByRole("button", { name: "Làm reel từ bài này" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Tạo video" }).click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);
});

test("Bài viết: only a Page's owner is offered it to post to", async ({ page, browser }) => {
  await loginAsSeed(page);
  await connectFacebook(page);
  await addUser(page, "binh@doi.vn", "Trần Bình", "mat-khau-tam-1");
  const binh = await (await browser.newContext({ baseURL: "http://localhost:3100", locale: "vi-VN" })).newPage();
  await login(binh, "binh@doi.vn", "mat-khau-tam-1");
  await binh.getByLabel("Mật khẩu mới", { exact: true }).fill("binh-moi-1234");
  await binh.getByLabel("Nhập lại mật khẩu mới").fill("binh-moi-1234");
  await binh.getByRole("button", { name: "Lưu mật khẩu mới" }).click();
  await expect(binh).toHaveURL(/\/videos$/);
  await binh.getByRole("menuitem", { name: "Bài viết" }).click();
  await binh.getByRole("button", { name: "Tạo bài viết" }).click();
  const drawer = binh.getByRole("dialog", { name: "Tạo bài viết" });
  await drawer.getByLabel("Chủ đề của bài").fill("ngâm chân nước gừng");
  await drawer.getByRole("button", { name: "Tạo bài" }).click();
  await expect(binh).toHaveURL(/\/articles\/\d+$/);
  const caption = binh.getByLabel("Caption");
  await caption.fill("Ngâm chân nước gừng trước khi ngủ\n\nTham khảo, không thay thế tư vấn bác sĩ.");
  await caption.blur();
  await expect(binh.getByText("Chưa có caption", { exact: true })).toBeHidden();
  // An's Page is in use, but Bình does not own it: it is not offered, and Bình is told how to get a Page.
  await binh.getByRole("button", { name: /^send Đăng$/ }).click();
  const publish = binh.getByRole("dialog", { name: "Đăng bài viết" });
  await expect(publish.getByTestId("no-page-of-mine")).toContainText("Chỉ chủ Page mới đăng lên Page đó");
  await expect(publish.getByLabel("Fanpage")).toHaveCount(0);
});

test("Bài viết: a Page's 30-day plan is set up, filled from a file, and an article made from a script", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await connectFacebook(page);
  await page.getByRole("menuitem", { name: "Bài viết" }).click();
  await page.getByText("Kế hoạch 30 ngày", { exact: true }).click();
  const plan = page.getByTestId("article-plan");
  // No plan yet: its owner starts on "Thiết lập".
  const settings = plan.getByTestId("plan-settings");
  const today = new Date(Date.now() + 7 * 3_600_000).toISOString().slice(0, 10);
  await settings.getByLabel("Ngày bắt đầu").fill(today);
  await settings.getByRole("button", { name: "Lưu" }).click();
  await expect(plan.getByTestId("plan-summary")).toHaveText(
    "Đã làm 0/90, đã lên lịch 0, ngày còn trống 30 · Backlog 0",
  );

  await plan.getByRole("button", { name: "Nhập file JSON/CSV" }).click();
  const dialog = page.getByRole("dialog", { name: /Nhập file JSON\/CSV/ });
  await dialog.locator('input[type="file"]').setInputFiles({
    name: "ke-hoach.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "day,slot,hook,body,cta,hashtags,image_brief,format,topic_group\n" +
        "1,1,Bữa sáng 10 phút,Sáng nào cũng vội?,Bạn ăn sáng món gì?,#ansang,,Mẹo,\n" +
        ",,Uống nước lúc nào?,Nội dung,,,,,\n" +
        "2,1,Thiếu body,,,,,,\n",
    ),
  });
  await expect(dialog.getByText("2 hợp lệ", { exact: true })).toBeVisible();
  await expect(dialog.getByText("1 lỗi", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Thiếu body", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Lưu kế hoạch (2 dòng)" }).click();
  await expect(dialog).toBeHidden();
  await expect(plan.getByTestId("plan-summary")).toHaveText(
    "Đã làm 0/90, đã lên lịch 0, ngày còn trống 30 · Backlog 1",
  );
  await expect(plan.getByTestId("plan-backlog")).toContainText("Uống nước lúc nào?");

  await plan.getByRole("button", { name: "Ngày 1 khung 1: Bữa sáng 10 phút" }).click();
  const drawer = page.getByRole("dialog", { name: /Ngày 1 · Khung 1/ });
  await drawer.getByRole("button", { name: "Tạo bài từ ô này" }).click();
  await expect(page).toHaveURL(/\/articles\/\d+$/);
  await expect(page.getByLabel("Caption")).toHaveValue("Bữa sáng 10 phút\n\nSáng nào cũng vội?\n\nBạn ăn sáng món gì?");
});
