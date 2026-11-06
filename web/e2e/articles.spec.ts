import { expect, test } from "@playwright/test";
import { connectFacebook, loginAsSeed, resetDatabase } from "./helpers";

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

  await page.getByRole("button", { name: "Xanh lá" }).click();
  await expect(page.getByText("Đang dùng: Thẻ chữ")).toBeVisible();
  await expect(preview.getByRole("img", { name: "Ảnh của bài" })).toBeVisible();
  await page.getByRole("button", { name: "Bỏ ảnh" }).click();
  await expect(page.getByText("Chưa có ảnh: bài sẽ đăng dạng chỉ chữ.")).toBeVisible();

  await page.getByRole("link", { name: "Về danh sách bài viết" }).click();
  await expect(page.getByRole("link", { name: "Ngủ đủ giấc quan trọng hơn bạn nghĩ" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Kiến thức ngắn" })).toBeVisible();
});

test("Bài viết: post a text article to a Page, read its numbers, take it down, and make a reel from it", async ({
  page,
}) => {
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

  await page.getByRole("button", { name: /^send Đăng$/ }).click();
  const publish = page.getByRole("dialog", { name: "Đăng bài viết" });
  // The one Page in use is already picked.
  await publish.getByRole("button", { name: "Đăng", exact: true }).click();
  await expect(page.getByTestId("article-status")).toHaveText("Đã đăng", { timeout: 60_000 });
  const post = page.getByTestId("article-post");
  await expect(post.getByText("Trang Dưỡng Sinh")).toBeVisible();
  await expect(post.getByRole("link", { name: "Xem bài" })).toBeVisible();
  await expect(post.getByText("chưa đo 48h")).toBeVisible();

  await post.getByRole("button", { name: "Cập nhật số" }).click();
  await expect(post.getByText(/Mới nhất .*30 cảm xúc · 6 bình luận · 2 chia sẻ · reach 400/)).toBeVisible({
    timeout: 30_000,
  });

  // The same caption cannot go on the same Page twice.
  await page.getByRole("button", { name: /^send Đăng$/ }).click();
  await publish.getByRole("button", { name: "Đăng", exact: true }).click();
  await expect(page.getByText("Nội dung này đã đăng hoặc đã hẹn trên Page này, không đăng lại được")).toBeVisible();
  await publish.getByRole("button", { name: "Huỷ" }).click();

  await post.getByRole("button", { name: "Gỡ bài" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Gỡ bài" }).click();
  await expect(post.getByText("Đã gỡ")).toBeVisible({ timeout: 60_000 });

  await page.getByRole("button", { name: "Làm reel từ bài này" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Tạo video" }).click();
  await expect(page).toHaveURL(/\/videos\/\d+$/);
});
