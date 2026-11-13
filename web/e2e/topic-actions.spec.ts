import { expect, test, type Page } from "@playwright/test";
import { chooseOption, loginAsSeed, resetDatabase } from "./helpers";

// Kho kiến thức: deleting a video from its group's list, moving a video to another group, and deleting ideas of the
// 30-day plan together.
test.beforeEach(() => resetDatabase());

async function healthGroup(page: Page): Promise<number> {
  const knowledge = await (await page.request.get("/api/knowledge")).json();
  return knowledge.topics.find((topic: { name: string }) => topic.name === "Sức khỏe").id;
}

async function handWritten(page: Page, group: number, topic: string): Promise<number> {
  const made = await page.request.post("/api/videos", {
    data: { topic, knowledge_topic_id: group, mode: "manual", script: `${topic}\nĐọc: ${topic}.` },
    headers: { Origin: new URL(page.url()).origin },
  });
  expect(made.status()).toBe(201);
  return (await made.json()).id;
}

test("a group's list deletes the maker's video after asking", async ({ page }) => {
  await loginAsSeed(page);
  const group = await healthGroup(page);
  await handWritten(page, group, "Rau dền luộc");
  await handWritten(page, group, "Canh mồng tơi");
  await page.goto(`/knowledge?group=${group}`);
  const health = page.locator('[data-topic="Sức khỏe"]');
  // No bin beside the row: "Xóa video" is in the row's actions, as for everything else done to a video.
  await expect(health.getByRole("button", { name: "Xóa video Rau dền luộc" })).toHaveCount(0);

  await health.getByRole("button", { name: "Thao tác với video Rau dền luộc" }).click();
  await page.getByRole("menuitem", { name: "Xóa video", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: "Xóa video “Rau dền luộc”?" });
  await confirm.getByRole("button", { name: "Xóa" }).click();
  await expect(page.getByText("Đã xóa video")).toBeVisible();
  await expect(health.getByRole("link", { name: "Rau dền luộc" })).toHaveCount(0);
  await expect(health.getByRole("link", { name: "Canh mồng tơi" })).toBeVisible();
});

test("the video page moves a video to another group", async ({ page }) => {
  await loginAsSeed(page);
  const group = await healthGroup(page);
  await page.goto("/knowledge");
  await page.getByLabel("Tên nhóm chủ đề mới").fill("Già Mà Khỏe");
  await page.getByRole("button", { name: "Thêm nhóm" }).click();
  await expect(page.getByRole("button", { name: /Già Mà Khỏe/ })).toBeVisible();
  const id = await handWritten(page, group, "Bí đỏ hấp");

  await page.goto(`/videos/${id}`);
  await page.getByRole("button", { name: "Thao tác khác với video" }).click();
  await page.getByRole("menuitem", { name: "Chuyển sang nhóm khác" }).click();
  const drawer = page.getByRole("dialog", { name: "Chuyển sang nhóm khác" });
  await chooseOption(page, drawer.getByLabel("Nhóm chủ đề mới"), "Già Mà Khỏe");
  await drawer.getByRole("button", { name: "Chuyển nhóm" }).click();
  await expect(page.getByText("Đã chuyển video sang nhóm “Già Mà Khỏe”")).toBeVisible();
  await expect(page.getByText(/nhóm Già Mà Khỏe, tạo bởi/)).toBeVisible();
});

test("30-day plan: ideas are ticked by day and deleted together", async ({ page }) => {
  await loginAsSeed(page);
  const group = await healthGroup(page);
  const headers = { Origin: new URL(page.url()).origin };
  for (const [day, topic] of [
    [1, "Uống nước ấm buổi sáng"],
    [1, "Ăn sáng trước 8 giờ"],
    [2, "Đi bộ sau bữa tối"],
  ] as const) {
    const added = await page.request.post(`/api/plans/${group}/items`, {
      data: { day, topic, pain_group: "", pain: "", hook: "" },
      headers,
    });
    expect(added.ok()).toBe(true);
  }
  await page.goto(`/knowledge?group=${group}&tab=plan`);
  const health = page.locator('[data-topic="Sức khỏe"]');
  await health.getByRole("button", { name: "Xóa nhiều ý tưởng" }).click();
  const drawer = page.getByRole("dialog", { name: "Xóa nhiều ý tưởng" });
  // Ticking day 1 ticks both of its ideas.
  await drawer
    .locator(".ant-tree-treenode", { hasText: /^Ngày 1/ })
    .locator(".ant-tree-checkbox")
    .click();
  await expect(drawer.getByTestId("plan-bulk-count")).toHaveText("Đã chọn 2 ý tưởng");
  await drawer.getByRole("button", { name: "Xóa 2 ý tưởng" }).click();
  await expect(page.getByText("Đã xóa 2 ý tưởng")).toBeVisible();
  await expect(drawer).toBeHidden();
  const plan = await (await page.request.get(`/api/plans/${group}`)).json();
  expect(plan.items.map((item: { topic: string }) => item.topic)).toEqual(["Đi bộ sau bữa tối"]);
});

test("a group's video list has the member's own auto-approve switch", async ({ page }) => {
  await loginAsSeed(page);
  const group = await healthGroup(page);
  await page.goto(`/knowledge?group=${group}`);
  const health = page.locator('[data-topic="Sức khỏe"]');
  const switcher = health.getByRole("switch", { name: "Tự duyệt khi render xong" });
  await expect(switcher).not.toBeChecked();
  await switcher.click();
  await expect(page.getByText("Đã bật tự duyệt")).toBeVisible();
  await page.reload();
  await expect(health.getByRole("switch", { name: "Tự duyệt khi render xong" })).toBeChecked();
});

test("Kho kiến thức: groups are chips with a mine filter, the status is tabs, and the menu folds away", async ({
  page,
}) => {
  await loginAsSeed(page);
  const group = await healthGroup(page);
  await handWritten(page, group, "Rau dền luộc");
  await page.goto(`/knowledge?group=${group}`);
  const health = page.locator('[data-topic="Sức khỏe"]');

  // The status is a tab with its count; "Đã đăng" holds none of the drafts.
  await expect(health.getByRole("tab", { name: "Tất cả (1)" })).toBeVisible();
  await health.getByRole("tab", { name: /^Đã đăng/ }).click();
  await expect(health.getByRole("link", { name: "Rau dền luộc" })).toHaveCount(0);
  await expect(page).toHaveURL(/status=posted/);
  await health.getByRole("tab", { name: /^Tất cả/ }).click();
  await expect(health.getByRole("link", { name: "Rau dền luộc" })).toBeVisible();

  // "Của tôi" keeps the chosen group and the groups the member made; "Cả đội" brings every group back.
  const list = page.getByTestId("topic-list");
  await page.getByText("Của tôi", { exact: true }).click();
  await expect(list.getByRole("button", { name: /Sức khỏe/ })).toHaveAttribute("aria-current", "true");
  await page.getByText("Cả đội", { exact: true }).click();
  await expect(list.getByRole("button").first()).toBeVisible();

  // The menu folds away for a wider table and comes back, and a reload remembers it.
  const menu = page.getByRole("link", { name: "Kho kiến thức" }).first();
  await expect(menu).toBeVisible();
  await page.getByRole("button", { name: "Ẩn menu" }).click();
  await expect(page.getByRole("button", { name: "Hiện menu" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Hiện menu" })).toBeVisible();
  await page.getByRole("button", { name: "Hiện menu" }).click();
  await expect(page.getByRole("button", { name: "Ẩn menu" })).toBeVisible();
});
