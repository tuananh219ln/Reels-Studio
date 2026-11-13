import { expect, test } from "@playwright/test";
import { chooseOption, connectFacebook, loginAsSeed, resetDatabase } from "./helpers";

test.beforeEach(() => resetDatabase());

test.afterEach(async ({ page }, info) => {
  if (info.status === info.expectedStatus)
    await page.screenshot({ path: info.outputPath("shared-actions.png"), animations: "disabled" });
});

test("shared actions: article list offers posting, making a Reel and deletion", async ({ page }) => {
  await loginAsSeed(page);
  let releaseKnowledge: () => void = () => {};
  const knowledgeReady = new Promise<void>((resolve) => {
    releaseKnowledge = resolve;
  });
  await page.route("**/api/knowledge", async (route) => {
    await knowledgeReady;
    await route.continue();
  });
  await page.goto("/articles");
  await page.getByRole("button", { name: "Tạo bài viết" }).click();
  const create = page.getByRole("dialog", { name: "Tạo bài viết" });
  await create.getByLabel("Chủ đề của bài").fill("Bài kiểm tra thao tác dùng chung");
  try {
    await expect(create.getByRole("button", { name: "Tạo bài", exact: true })).toBeDisabled();
  } finally {
    releaseKnowledge();
  }
  await create.getByRole("button", { name: "Tạo bài", exact: true }).click();
  await expect(page).toHaveURL(/\/articles\/\d+$/);
  await page.goto("/articles");
  const row = page.getByRole("row").filter({ hasText: "Bài kiểm tra thao tác dùng chung" });
  await expect(row.getByRole("button", { name: "Đăng bài", exact: true })).toBeVisible();
  await expect(row.getByRole("button", { name: "Làm reel từ bài này" })).toBeVisible();
  await row.getByRole("button", { name: "Xoá bài viết" }).click();
  await page.getByRole("button", { name: "Xoá", exact: true }).last().click();
  await expect(row).toHaveCount(0);
});

test("shared actions: Page dashboard can replace its token without leaving the Page", async ({ page }) => {
  await loginAsSeed(page);
  await connectFacebook(page);
  await page.goto("/fanpages");
  await page.getByRole("link", { name: "Trang Dưỡng Sinh" }).click();
  await page.getByRole("button", { name: "Thao tác với Trang Dưỡng Sinh" }).click();
  await page.getByText("Dán token mới", { exact: true }).click();
  await expect(page.getByRole("dialog", { name: /token/i })).toBeVisible();
  await expect(page).toHaveURL(/\/fanpages\/\d+/);
});

test("shared actions: Page logo controls are shared by cards and the dashboard", async ({ page }) => {
  await loginAsSeed(page);
  await connectFacebook(page);
  await page.goto("/fanpages");
  await expect(page.getByTestId("fanpage-card").getByTestId("fanpage-logo")).toBeVisible();
  await page.getByRole("link", { name: "Trang Dưỡng Sinh" }).click();
  await page.getByRole("button", { name: "Thao tác với Trang Dưỡng Sinh" }).click();
  await page.getByText("Tài khoản và chủ Page", { exact: true }).click();
  const settings = page.getByRole("dialog", { name: /Tài khoản và chủ Page/ });
  await expect(settings.getByTestId("fanpage-logo")).toBeVisible();
  await expect(settings.getByRole("button", { name: "Tải logo", exact: true })).toBeVisible();
});

test("shared actions: video lists open the same actions without navigating to the editor", async ({ page }) => {
  await loginAsSeed(page);
  const knowledge = await (await page.request.get("/api/knowledge")).json();
  const made = await page.request.post("/api/videos", {
    headers: { Origin: new URL(page.url()).origin },
    data: {
      topic: "Video thao tác dùng chung",
      knowledge_topic_id: knowledge.topics[0].id,
      mode: "manual",
      script: "Một cảnh tự viết",
    },
  });
  expect(made.ok()).toBeTruthy();
  await page.reload();
  await page.getByRole("button", { name: "Thao tác với video Video thao tác dùng chung" }).click();
  await expect(page.getByRole("menuitem", { name: "Nhân bản", exact: true })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Chuyển sang nhóm khác" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Xóa video", exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/videos$/);
});

test("shared actions: a group's media has library filters, bulk tagging and owner deletion", async ({ page }) => {
  await loginAsSeed(page);
  const headers = { Origin: new URL(page.url()).origin };
  const pixel = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a4R8AAAAASUVORK5CYII=",
    "base64",
  );
  for (const name of ["shared-first.png", "shared-second.png"]) {
    const made = await page.request.post("/api/media", {
      headers,
      multipart: { file: { name, mimeType: "image/png", buffer: pixel }, folder: "shared-media" },
    });
    expect(made.status()).toBe(201);
  }
  await page.goto("/knowledge");
  await page.getByRole("button", { name: /Sức khỏe/ }).click();
  const group = page.locator('[data-topic="Sức khỏe"]');
  await group.getByRole("tab", { name: "Tư liệu" }).click();
  await group.getByRole("button", { name: "Liên kết thư mục" }).click();
  const link = page.getByRole("dialog", { name: "Liên kết thư mục cho nhóm “Sức khỏe”" });
  await chooseOption(page, link.getByLabel("Thư mục của nhóm"), "shared-media (2)");
  await link.getByRole("button", { name: "Liên kết thư mục" }).click();
  await expect(group.getByTestId("media-item")).toHaveCount(2);
  await group.getByLabel("Tìm tư liệu theo tên").fill("shared-first");
  await expect(group.getByTestId("media-item")).toHaveCount(1);
  await group.getByLabel("Tìm tư liệu theo tên").clear();
  await expect(group.getByTestId("media-item")).toHaveCount(2);
  await group.getByRole("button", { name: "Chọn tất cả", exact: true }).click();
  await group.getByTestId("media-selection").getByRole("button", { name: "Thêm thẻ" }).click();
  const tags = page.getByRole("dialog", { name: "Thêm thẻ cho 2 tư liệu" });
  await expect(tags).toBeVisible();
  await tags.getByRole("button", { name: "Huỷ", exact: true }).click();
  await group.getByRole("button", { name: "Xoá shared-first.png", exact: true }).click();
  await page.getByRole("button", { name: "Xoá", exact: true }).last().click();
  await expect(group.getByTestId("media-item")).toHaveCount(1);
  expect((await (await page.request.get("/api/media?folder=shared-media")).json()).items[0].name).toBe(
    "shared-second.png",
  );
});

test("shared actions: the job log retries and cancels eligible work in place", async ({ page }) => {
  await loginAsSeed(page);
  const me = await (await page.request.get("/api/me")).json();
  let status = "failed";
  let retried = 0;
  let cancelled = 0;
  await page.route("**/api/jobs**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/jobs" && route.request().method() === "GET") {
      return route.fulfill({
        json: [
          {
            id: 98765,
            video_id: null,
            knowledge_topic_id: 1,
            article_id: null,
            video_title: "Job kiểm tra thao tác",
            kind: "plan",
            kind_label: "Kế hoạch 30 ngày",
            status,
            created_by: me.name,
            created_by_id: me.id,
            created_at: new Date().toISOString(),
            started_at: null,
            duration_seconds: null,
            claude_calls: 0,
            image_calls: 0,
            llm: null,
            error: status === "failed" ? "Lỗi dịch vụ giả" : null,
            can_cancel: status === "queued",
          },
        ],
      });
    }
    if (url.pathname === "/api/jobs/98765/retry" && route.request().method() === "POST") {
      retried += 1;
      status = "queued";
      return route.fulfill({ json: {} });
    }
    if (url.pathname === "/api/jobs/98765/cancel" && route.request().method() === "POST") {
      cancelled += 1;
      status = "cancelled";
      return route.fulfill({ json: {} });
    }
    return route.continue();
  });
  await page.goto("/jobs");
  const row = page.getByRole("row").filter({ hasText: "Job kiểm tra thao tác" });
  await row.getByRole("button", { name: "Thử lại", exact: true }).click();
  await expect(page.getByText("Job sẽ chạy lại qua worker; các dịch vụ AI có thể phát sinh chi phí.")).toBeVisible();
  await page.locator(".ant-popover").getByRole("button", { name: "Thử lại", exact: true }).click();
  await expect(row.getByRole("button", { name: "Hủy job", exact: true })).toBeVisible();
  expect(retried).toBe(1);
  await row.getByRole("button", { name: "Hủy job", exact: true }).click();
  await page.locator(".ant-popover").getByRole("button", { name: "Hủy job", exact: true }).click();
  await expect(row).toContainText("Đã hủy");
  await expect(row.getByRole("button", { name: "Hủy job", exact: true })).toHaveCount(0);
  expect(cancelled).toBe(1);
  await expect(page).toHaveURL(/\/jobs$/);
});

test("shared actions: a Page owner can take down a teammate's reel from the posts list", async ({ page }) => {
  await loginAsSeed(page);
  const me = await (await page.request.get("/api/me")).json();
  let takeDown = 0;
  const post = {
    id: 98764,
    status: "published",
    fanpage: "Page của tôi",
    scheduled_at: null,
    at: new Date().toISOString(),
    url: "https://www.facebook.com/reel/98764",
    created_by: "Đồng đội",
    created_by_id: me.id + 100,
    fanpage_owner_id: me.id,
    closed_at: null,
    closed_by: null,
    metrics: {
      latest: null,
      at_48h: null,
      error: null,
      pending: false,
      analysis: { median_views: null, samples: 0, times_median: null, share_rate: null },
      length_seconds: 3,
      scenes: [],
    },
    comment: { state: "off", auto: false, error: null, text: null, extra_count: 0, at: null },
    video_id: 98764,
    title: "Bài của đồng đội trên Page của tôi",
    thumbnail_url: null,
    busy: false,
    attempt: null,
  };
  await page.route("**/api/posts", (route) => route.fulfill({ json: [post] }));
  await page.route("**/api/posts/98764/take-down", (route) => {
    takeDown += 1;
    return route.fulfill({ json: {} });
  });
  await page.goto("/posts");
  // The last cell: the middle of the row now lands on the video title, which opens the video.
  await page.getByTestId("post-group").getByRole("cell").last().click();
  const posts = page.getByTestId("post-rows");
  await expect(posts.getByRole("button", { name: "Xóa", exact: true })).toBeEnabled();
  await posts.getByRole("button", { name: "Xóa", exact: true }).click();
  await page.locator(".ant-popover").getByRole("button", { name: "Xóa", exact: true }).click();
  await expect.poll(() => takeDown).toBe(1);
  await expect(page).toHaveURL(/\/posts$/);
});

test("shared actions: approval confirms the latest plan time, not an older list snapshot", async ({ page }) => {
  await loginAsSeed(page);
  const me = await (await page.request.get("/api/me")).json();
  const row = {
    id: 98763,
    topic: "Duyệt theo lịch mới",
    title: "Duyệt theo lịch mới",
    platform: "facebook",
    variant_of_id: null,
    tiktok_posted: false,
    posted_on: [],
    has_tiktok_version: false,
    cloned: false,
    created_by: me.name,
    created_by_id: me.id,
    created_at: new Date().toISOString(),
    status: "done",
    status_label: "Chờ đăng",
    post_stage: "ready",
    mp4_outdated: false,
    rerender_failed: false,
    thumbnail_url: null,
    knowledge_topic: "Sức khỏe",
    plan_day: 1,
    suggested_post_at: "2030-01-01T07:00:00+07:00",
    queue: null,
    post: null,
    made_via: "manual",
    assistant_app: "",
    mode: "slides",
    product_count: 0,
    content_type: "",
  };
  await page.route("**/api/videos?*", (route) => route.fulfill({ json: [row] }));
  await page.route("**/api/videos/98763", (route) =>
    route.fulfill({
      json: {
        ...row,
        knowledge_topic_id: 1,
        locked: false,
        mp4: { url: "/fake.mp4" },
        posted_fanpage_ids: [],
        fanpages: [{ id: 7, name: "Page của tôi", owner_id: me.id, knowledge_topic_id: 1 }],
        plan_idea: { suggested_post_at: "2030-01-02T08:00:00+07:00" },
      },
    }),
  );
  await page.goto("/videos");
  await page.getByTestId("video-card").getByRole("button", { name: "Duyệt", exact: true }).click();
  await expect(page.locator(".ant-popover")).toContainText("Duyệt đăng lúc 02/01/2030 08:00?");
  await page.locator(".ant-popover").getByRole("button", { name: "Huỷ", exact: true }).click();
});
