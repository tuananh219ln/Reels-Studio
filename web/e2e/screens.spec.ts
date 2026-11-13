import { expect, test, type Page } from "@playwright/test";
import { addUser, connectFacebook, login, loginAsSeed, resetDatabase } from "./helpers";

// The third screen review (2026-11-10): what the screens got wrong in logic, and lists that asked the api too often.
test.beforeEach(() => resetDatabase());

/** The seed's "Sức khỏe" group, through the api its pages use. */
async function healthGroup(page: Page): Promise<number> {
  const knowledge = await (await page.request.get("/api/knowledge")).json();
  return knowledge.topics.find((topic: { name: string }) => topic.name === "Sức khỏe").id;
}

test("phone width: Cả đội in the address is not counted as a filter", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await loginAsSeed(page);
  await page.goto("/videos?by=");
  // The button's name starts with its icon's: "filter Bộ lọc", never "… (1)".
  await expect(page.getByRole("button", { name: /Bộ lọc$/ })).toBeVisible();
});

test("Tạo video names the writer without a middle dot", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const line = page.getByRole("dialog", { name: "Tạo video" }).getByTestId("llm-line");
  await expect(line).toContainText("Viết bằng: ");
  await expect(line).not.toContainText("·");
});

test("Quản lý Page: the empty list's button is named apart, and an empty Trang của tôi points to the others", async ({
  page,
  browser,
}) => {
  await loginAsSeed(page);
  await page.goto("/fanpages?whose=mine");
  // No Page at all: said as such, even when "Trang của tôi" is in the address.
  await expect(page.getByText("Chưa kết nối Fanpage nào")).toBeVisible();
  await expect(page.getByRole("button", { name: "Thêm Fanpage" })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Kết nối Page đầu tiên" })).toBeVisible();

  // A teammate owns none: "Trang của tôi" offers the team's Pages, not a second "add".
  await connectFacebook(page);
  await addUser(page, "binh@doi.vn", "Trần Bình", "mat-khau-tam-1");
  const other = await (await browser.newContext({ baseURL: "http://localhost:3100", locale: "vi-VN" })).newPage();
  await login(other, "binh@doi.vn", "mat-khau-tam-1");
  await other.getByLabel("Mật khẩu mới", { exact: true }).fill("binh-moi-1234");
  await other.getByLabel("Nhập lại mật khẩu mới").fill("binh-moi-1234");
  await other.getByRole("button", { name: "Lưu mật khẩu mới" }).click();
  await expect(other).toHaveURL(/\/videos$/);
  await other.goto("/fanpages?whose=mine");
  await expect(other.getByText("Bạn chưa có Fanpage nào đang dùng")).toBeVisible();
  await expect(other.getByRole("button", { name: "Kết nối Page đầu tiên" })).toHaveCount(0);
  await other.getByRole("button", { name: "Xem tất cả Page" }).click();
  await expect(other.getByTestId("fanpage-card").filter({ hasText: "Trang Dưỡng Sinh" })).toBeVisible();
  await other.close();
});

test("30-day plan: an empty plan says which button asks the AI", async ({ page }) => {
  await loginAsSeed(page);
  await page.goto("/knowledge");
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const health = page.locator('[data-topic="Sức khỏe"]');
  await health.getByRole("tab", { name: "Kế hoạch 30 ngày" }).click();
  const empty = health.getByTestId("plan-empty");
  await expect(empty).toContainText("Bấm “Lập kế hoạch bằng AI”");
  await expect(empty.getByRole("button", { name: "Lập kế hoạch bằng AI" })).toBeVisible();
});

test("30-day plan: the day's filter counts the day's ideas, not the month's", async ({ page }) => {
  await loginAsSeed(page);
  const group = await healthGroup(page);
  await page.goto("/knowledge");
  const headers = { Origin: new URL(page.url()).origin };
  for (const [day, topic] of [
    [1, "Uống nước ấm buổi sáng"],
    [2, "Đi bộ sau bữa tối"],
  ] as const) {
    const added = await page.request.post(`/api/plans/${group}/items`, {
      data: { day, topic, pain_group: "", pain: "", hook: "" },
      headers,
    });
    expect(added.ok()).toBe(true);
  }
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const health = page.locator('[data-topic="Sức khỏe"]');
  await health.getByRole("tab", { name: "Kế hoạch 30 ngày" }).click();
  await health.getByRole("button", { name: "Chọn ngày 1", exact: true }).click();
  await expect(page.getByTestId("plan-matches")).toHaveText("1/1 ý tưởng của ngày khớp");
  await page.getByLabel("Tìm ý tưởng").fill("đi bộ");
  await expect(page.getByTestId("plan-matches")).toHaveText("0/1 ý tưởng của ngày khớp");
});

test("phone width: Kho kiến thức's groups are chips above the group, not a column beside it", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await loginAsSeed(page);
  await page.goto("/knowledge");
  const list = page.getByTestId("topic-list");
  await expect(list).toBeVisible();
  const box = await list.boundingBox();
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
});

test("Video: a video that cannot be loaded says so and offers Thử lại", async ({ page }) => {
  await loginAsSeed(page);
  let fail = true;
  await page.route(/\/api\/videos\/424242$/, (route) =>
    fail
      ? route.fulfill({ status: 500, contentType: "application/json", body: '{"detail":"Lỗi máy chủ"}' })
      : route.fallback(),
  );
  await page.goto("/videos/424242");
  await expect(page.getByText("Không tải được video")).toBeVisible();
  // The app's own words for a server that failed.
  await expect(page.getByText("Không kết nối được máy chủ, thử lại sau")).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "Thử lại" }).click();
  // The api now answers with its own 404 for a video that does not exist.
  await expect(page.getByRole("link", { name: "Về danh sách video" })).toBeVisible();
});

test("Bài viết: a list that cannot be read says so once, not on every refresh", async ({ page }) => {
  await loginAsSeed(page);
  await page.clock.install();
  await page.route(/\/api\/articles$/, (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: '{"detail":"Lỗi máy chủ"}' }),
  );
  await page.goto("/articles");
  const toast = page.locator(".ant-message-notice").filter({ hasText: "Không kết nối được máy chủ" });
  await expect(toast).toHaveCount(1);
  // Past the toast's own 3 seconds, then to the next refresh: the list is asked for again, quietly.
  await page.clock.runFor(4_000);
  await expect(toast).toHaveCount(0);
  const answered = page.waitForResponse(/\/api\/articles$/);
  await page.clock.runFor(60_000);
  await answered;
  // Read once, not waited for: an old refresh's toast would be on screen for its 3 seconds now.
  await page.waitForTimeout(300);
  expect(await toast.count()).toBe(0);
});

test("Video list: with nothing being made, the list is not asked for every few seconds", async ({ page }) => {
  await loginAsSeed(page);
  await page.clock.install();
  let asked = 0;
  page.on("request", (request) => {
    if (/\/api\/videos\?q=/.test(request.url())) asked += 1;
  });
  await page.goto("/videos");
  await expect(page.getByText("Chưa có video nào")).toBeVisible();
  await expect.poll(() => asked).toBeGreaterThan(0);
  const first = asked;
  await page.clock.runFor(20_000);
  // The old list asked every 5 seconds: four more times by now.
  await page.waitForTimeout(500);
  expect(asked).toBe(first);
});
