import { expect, test, type Page } from "@playwright/test";
import { loginAsSeed, resetDatabase } from "./helpers";

// Kho kiến thức: the "Tài liệu" tab (Markdown documents of a group), the "Lịch đăng" tab that only links to Quản lý
// kênh, and the empty posting slots of a plan day.
test.beforeEach(() => resetDatabase());

async function healthGroup(page: Page): Promise<number> {
  const knowledge = await (await page.request.get("/api/knowledge")).json();
  return knowledge.topics.find((topic: { name: string }) => topic.name === "Sức khỏe").id;
}

test("a group's documents are added, read as Markdown, searched and pinned", async ({ page }) => {
  await loginAsSeed(page);
  const group = await healthGroup(page);
  await page.goto(`/knowledge?group=${group}`);
  await page.getByRole("tab", { name: "Tài liệu" }).click();
  const docs = page.getByTestId("topic-docs");
  await expect(docs).toContainText("Nhóm này chưa có tài liệu nào");

  await docs.getByRole("button", { name: "Thêm tài liệu" }).click();
  const dialog = page.getByRole("dialog", { name: "Thêm tài liệu" });
  await dialog.getByLabel("Tên file").fill("mau-chung-test.md");
  await dialog
    .getByLabel("Nội dung (Markdown)")
    .fill("# Mẫu chung TEST\n\n| Khung | Việc |\n| --- | --- |\n| 0 | Lưới collage |");
  await dialog.getByRole("button", { name: "Lưu" }).click();
  await expect(page.getByText("Đã lưu tài liệu")).toBeVisible();

  const reader = docs.getByTestId("doc-reader");
  await expect(reader.getByRole("heading", { name: "Mẫu chung TEST" })).toBeVisible();
  await expect(reader.getByRole("cell", { name: "Lưới collage" })).toBeVisible();
  await expect(docs.getByTestId("doc-row")).toContainText("An");

  await docs.getByLabel("Tìm tài liệu").fill("luoi collage");
  await expect(docs.getByTestId("doc-row")).toHaveCount(1);
  await docs.getByLabel("Tìm tài liệu").fill("khong co");
  await expect(docs.getByTestId("doc-row")).toHaveCount(0);
  await docs.getByLabel("Tìm tài liệu").fill("");

  await docs.getByRole("button", { name: "Ghim", exact: true }).click();
  await expect(docs.getByRole("button", { name: "Bỏ ghim" })).toBeVisible();

  const listed = await (await page.request.get(`/api/topic-docs?topic_id=${group}`)).json();
  expect(listed.docs[0]).toMatchObject({ name: "mau-chung-test.md", pinned: true });
});

test("the group's Lịch đăng tab only links to the Page's own", async ({ page }) => {
  await loginAsSeed(page);
  const group = await healthGroup(page);
  await page.goto(`/knowledge?group=${group}&tab=schedule`);
  // The tab's own empty state: the group's "Sẵn sàng tạo video" box says the first half too once it has loaded.
  await expect(
    page.getByText("Chưa có Page nào đăng nhóm này. Chọn nhóm cho Page ở Quản lý kênh, tab Lịch đăng."),
  ).toBeVisible();
});
