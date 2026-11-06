import { expect, test } from "@playwright/test";
import { loginAsSeed, resetDatabase } from "./helpers";

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
  await expect(caption).toHaveValue(/Tham khảo, không thay thế tư vấn bác sĩ\.$/);
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
