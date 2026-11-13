import { expect, test } from "@playwright/test";
import { loginAsSeed, openPanel, resetDatabase } from "./helpers";

// "Bình luận thêm" under "Bình luận ghim" on a video's "Nội dung đăng": added, kept, edited and removed.
test.beforeEach(() => resetDatabase());

test("a video's extra comments are added one by one, kept and removed", async ({ page }) => {
  await loginAsSeed(page);
  const knowledge = await (await page.request.get("/api/knowledge")).json();
  const made = await page.request.post("/api/videos", {
    data: {
      topic: "Bí đỏ hấp",
      knowledge_topic_id: knowledge.topics[0].id,
      mode: "manual",
      script: "Bí đỏ\nĐọc: bí đỏ.",
    },
    headers: { Origin: new URL(page.url()).origin },
  });
  const id = (await made.json()).id;

  await page.goto(`/videos/${id}`);
  await page.getByRole("tab", { name: "Đăng bài" }).click();
  await openPanel(page, "Bình luận");
  const extra = page.getByTestId("extra-comments");
  for (const text of ["Nhà bạn hay nấu bí đỏ thế nào?", "Lưu lại cho cuối tuần nhé!"]) {
    await extra.getByRole("button", { name: "Thêm bình luận" }).click();
    await extra.getByLabel("Bình luận mới").fill(text);
    await extra.getByRole("button", { name: "Lưu bình luận" }).click();
    await expect(extra.getByLabel("Bình luận mới")).toHaveCount(0);
  }
  await expect(extra.getByRole("textbox", { name: "Bình luận 2" })).toHaveValue("Nhà bạn hay nấu bí đỏ thế nào?");
  await expect(extra.getByRole("textbox", { name: "Bình luận 3" })).toHaveValue("Lưu lại cho cuối tuần nhé!");

  await page.reload();
  await page.getByRole("tab", { name: "Đăng bài" }).click();
  await openPanel(page, "Bình luận");
  await extra.getByRole("button", { name: "Bỏ bình luận 2" }).click();
  await expect(extra.getByRole("textbox", { name: "Bình luận 2" })).toHaveValue("Lưu lại cho cuối tuần nhé!");
  await expect(extra.getByRole("textbox", { name: "Bình luận 3" })).toHaveCount(0);
  const saved = await (await page.request.get(`/api/videos/${id}`)).json();
  expect(saved.extra_comments).toEqual(["Lưu lại cho cuối tuần nhé!"]);
});
