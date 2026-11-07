import { expect, test, type Page } from "@playwright/test";
import { addUser, chooseOption, connectFacebook, login, loginAsSeed, resetDatabase } from "./helpers";

// Issue #47. Shopee is the fake one (api/scripts/fake_services.py), which knows this App ID and Secret.
const APP_ID = "1000001";
const SECRET = "fake-shopee-secret";

test.beforeEach(() => resetDatabase());

async function addShopeeAccount(page: Page) {
  await page.goto("/settings/affiliate-accounts");
  await page.getByRole("button", { name: "Thêm tài khoản" }).click();
  const dialog = page.getByRole("dialog", { name: "Thêm tài khoản affiliate" });
  await dialog.getByLabel("Tên tài khoản").fill("Shopee của An");
  await dialog.getByLabel("App ID").fill(APP_ID);
  await dialog.getByLabel("Secret").fill(SECRET);
  await dialog.getByRole("button", { name: "Thêm" }).click();
  await expect(page.getByText("Secret …cret")).toBeVisible();
}

test("a member's Shopee account: added, checked, set on their Page, and hidden from others", async ({
  page,
  browser,
}) => {
  await loginAsSeed(page);
  await addShopeeAccount(page);
  await page.getByRole("button", { name: "Kiểm tra kết nối" }).click();
  await expect(page.getByText("Shopee nhận App ID và Secret này")).toBeVisible();

  await connectFacebook(page);
  await page.getByRole("menuitem", { name: "Quản lý Page" }).click();
  const owner = page.getByTestId("fanpage-card").getByTestId("fanpage-owner");
  await expect(owner).toContainText("Thuộc: bạn");
  await chooseOption(page, owner.getByLabel("Tài khoản Shopee của Trang Dưỡng Sinh"), "Shopee: Shopee của An");
  await expect(owner.getByLabel("Tài khoản Shopee của Trang Dưỡng Sinh")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("fanpage-owner")).toContainText("Shopee: Shopee của An");

  await addUser(page, "binh@doi.vn", "Trần Bình", "mat-khau-tam-1");
  const binh = await (await browser.newContext({ baseURL: "http://localhost:3100", locale: "vi-VN" })).newPage();
  await login(binh, "binh@doi.vn", "mat-khau-tam-1");
  await binh.getByLabel("Mật khẩu mới", { exact: true }).fill("binh-moi-1234");
  await binh.getByLabel("Nhập lại mật khẩu mới").fill("binh-moi-1234");
  await binh.getByRole("button", { name: "Lưu mật khẩu mới" }).click();
  await expect(binh).toHaveURL(/\/videos$/);
  await binh.goto("/settings/affiliate-accounts");
  await expect(binh.getByText("Chưa có tài khoản nào")).toBeVisible();
  await binh.goto("/fanpages");
  await expect(binh.getByTestId("fanpage-owner")).toHaveText("Thuộc: Nguyễn Văn An");
  await binh.goto("/affiliate");
  await binh.getByRole("tab", { name: "Doanh thu" }).click();
  await expect(binh.getByText("Chưa có tài khoản Shopee nào của bạn")).toBeVisible();
});

test("a new script finds Shopee products with the writer's account, and one is chosen", async ({ page }) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await addShopeeAccount(page);
  await page.goto("/videos");
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("xương khớp");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page.getByTestId("scene").first()).toBeVisible({ timeout: 90_000 });

  await page.getByRole("tab", { name: "Nội dung đăng" }).click();
  const suggestions = page.getByTestId("shopee-suggestions");
  const products = suggestions.getByTestId("suggested-product");
  // Two ideas from the script, two products meeting the rules each (the fake's third has 4.2 stars).
  await expect(products).toHaveCount(4, { timeout: 30_000 });
  await expect(suggestions).toContainText("Sữa hạt canxi");
  const first = products.filter({ hasText: "Sữa hạt canxi loại 1" });
  await expect(first).toContainText("hoa hồng 8%");
  await first.getByRole("button", { name: "Chọn" }).click();
  await expect(first.getByText("Đã chọn")).toBeVisible();
  await expect(page.locator(".ant-select-selection-item", { hasText: "Sữa hạt canxi loại 1" })).toBeVisible();

  await page.goto("/affiliate");
  await page.getByRole("tab", { name: "Sản phẩm" }).click();
  const row = page.getByRole("row", { name: /Sữa hạt canxi loại 1/ });
  await expect(row).toContainText("Đã duyệt");
  await expect(row).toContainText("Tìm qua API");
});

test("without an App ID, an affiliate link pasted on the video is filled in by hand and chosen", async ({ page }) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await page.goto("/videos");
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("xương khớp");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page.getByTestId("scene").first()).toBeVisible({ timeout: 90_000 });

  await page.getByRole("tab", { name: "Nội dung đăng" }).click();
  const suggestions = page.getByTestId("shopee-suggestions");
  await suggestions.getByLabel("Dán link aff Shopee").fill("https://s.shopee.vn/4LKghKN3cR");
  await suggestions.getByRole("button", { name: "Thêm link" }).click();
  const pasted = suggestions.getByTestId("suggested-product");
  await expect(pasted).toContainText("Chưa có thông tin sản phẩm");
  await expect(pasted.getByRole("button", { name: "Chọn" })).toHaveCount(0);

  await pasted.getByRole("button", { name: "Sửa thông tin" }).click();
  const form = page.getByRole("dialog", { name: "Sửa sản phẩm" });
  await form.getByLabel("Tên sản phẩm").fill("Hạt giống rau muống");
  await form.getByLabel("Tên shop").fill("Hồng Hà Seeds");
  await chooseOption(page, form.getByLabel("Loại shop"), "Shopee Mall");
  await form.getByLabel("Số sao").fill("4.9");
  await form.getByLabel("Lượt bán").fill("2500");
  await form.getByLabel("Giá (đ)").fill("45000");
  await form.getByLabel("Hoa hồng (%)").fill("8");
  await form.getByRole("button", { name: "Lưu" }).click();
  await expect(form).toBeHidden();
  await expect(pasted).toContainText("Hạt giống rau muống");
  await pasted.getByRole("button", { name: "Chọn" }).click();
  await expect(pasted.getByText("Đã chọn")).toBeVisible();
});

test("a pasted Shopee link is filled in by the worker and can be approved", async ({ page }) => {
  await loginAsSeed(page);
  await addShopeeAccount(page);
  await page.goto("/affiliate");
  await page.getByRole("tab", { name: "Sản phẩm" }).click();
  await page.getByRole("button", { name: "Thêm sản phẩm" }).click();
  const dialog = page.getByRole("dialog", { name: "Thêm sản phẩm" });
  await chooseOption(page, dialog.getByLabel("Nhóm chủ đề"), "Sức khỏe");
  // The fake offers any item it is asked for, as "Sản phẩm Shopee <id>" from a Mall shop with 4.9 stars.
  await dialog.getByLabel("Link sản phẩm").fill("https://shopee.vn/Hat-giong-rau-i.1346703635.45113237093");
  await dialog.getByRole("button", { name: "Thêm", exact: true }).click();
  await expect(dialog).toBeHidden();
  const product = page.getByRole("row", { name: /Sản phẩm Shopee 45113237093/ });
  await expect(product).toContainText("Shopee Mall", { timeout: 30_000 });
  await expect(product).toContainText("20.000đ/đơn");
  await product.getByRole("button", { name: "Duyệt" }).click();
  await expect(product).toContainText("Đã duyệt");
});

test("a TikTok version is its own video, linked both ways, with TikTok's posting kit", async ({ page }) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("tim mạch");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page.getByTestId("scene").first()).toBeVisible({ timeout: 90_000 });
  const source = page.url();

  // "Nhân bản › Bản cho Page khác" on "Bài đăng" opens the drawer with a variant request, and drops it from the address.
  await page.goto(`${source}?clone=page`);
  const variant = page.getByRole("dialog", { name: "Nhân bản video" });
  await expect(variant.getByLabel("Yêu cầu đổi")).toHaveValue(/Viết biến thể cho Page khác/);
  await expect(page).toHaveURL(source);
  await variant.getByRole("button", { name: "Huỷ" }).click();
  await expect(variant).toBeHidden();

  await page.getByRole("button", { name: "Tạo bản TikTok" }).click();
  const clone = page.getByRole("dialog", { name: "Tạo bản TikTok" });
  await expect(clone.getByLabel("Yêu cầu đổi")).toHaveValue(/Viết lại cho TikTok/);
  await clone.getByRole("button", { name: "Tạo bản TikTok" }).click();
  await expect(page).not.toHaveURL(source);
  await expect(page.getByTestId("video-platform")).toHaveText("TikTok");
  await expect(page.getByTestId("variants")).toContainText("Bản Facebook gốc:");
  await expect(page.getByRole("button", { name: "Tạo bản TikTok" })).toHaveCount(0);

  // On the list the version sits on its source's card, not on a card of its own, and opens from there.
  await page.getByRole("link", { name: "Danh sách video" }).click();
  await expect(page.getByTestId("video-card")).toHaveCount(1);
  // The source card says its own platform, so the TikTok link is not the only platform on it.
  await expect(page.getByTestId("video-card").getByTestId("video-platform")).toHaveText("Facebook");
  const version = page.getByTestId("video-version");
  await expect(version).toHaveText(/TikTok\s*Nháp/);
  await version.click();
  await expect(page.getByTestId("video-platform")).toHaveText("TikTok");
  await page.goBack();
  // Choosing a platform shows every video on its own card again.
  await chooseOption(page, page.getByLabel("Lọc theo nền tảng"), "TikTok");
  await expect(page.getByTestId("video-platform")).toHaveCount(1);
});

test("a member connects their TikTok account through TikTok's consent page, then disconnects it", async ({ page }) => {
  await loginAsSeed(page);
  // TikTok's consent page, answered as TikTok does once the member allows the app: back to the callback with a code
  // and the state the app sent. Any other TikTok address is never reached.
  await page.route("https://www.tiktok.com/**", (route) => {
    const asked = new URL(route.request().url());
    if (asked.pathname !== "/v2/auth/authorize/") {
      return route.abort();
    }
    expect(asked.searchParams.get("scope")).toBe("user.info.basic,video.upload,video.publish");
    expect(asked.searchParams.get("redirect_uri")).toBe("https://reels.quangdang.xyz/api/tiktok/oauth/callback");
    const back = `/api/tiktok/oauth/callback?code=fake-tiktok-code&state=${asked.searchParams.get("state")}`;
    return route.fulfill({ status: 302, headers: { location: `http://localhost:3100${back}` } });
  });
  await page.goto("/settings/affiliate-accounts");
  await page.getByRole("button", { name: "Kết nối TikTok" }).first().click();
  await expect(page.getByText("Đã kết nối tài khoản TikTok")).toBeVisible();
  await expect(page).toHaveURL(/\/settings\/affiliate-accounts$/);
  // The account is made from the TikTok profile and shows the connection, never a token.
  await expect(page.getByText("An Lành SK", { exact: true })).toBeVisible();
  await expect(page.getByTestId("tiktok-connection")).toContainText("Đã kết nối @anlanhsk");

  await page.getByRole("button", { name: "Ngắt kết nối" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Ngắt kết nối" }).click();
  await expect(page.getByText("Đã ngắt kết nối TikTok")).toBeVisible();
  await expect(page.getByTestId("tiktok-connection")).toHaveText("Chưa kết nối TikTok: chỉ ghi được bài đăng tay");
});

test("an article's AI caption finds Shopee products with the writer's account, and one goes in its comment", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await addShopeeAccount(page);
  await page.goto("/articles");
  await page.getByRole("button", { name: "Tạo bài viết" }).click();
  const drawer = page.getByRole("dialog", { name: "Tạo bài viết" });
  await drawer.getByLabel("Chủ đề của bài").fill("uống nước ấm buổi sáng");
  await drawer.getByRole("button", { name: "Tạo bài" }).click();
  await page.getByRole("button", { name: "AI viết" }).click();
  await expect(page.getByLabel("Gợi ý sản phẩm")).toHaveValue("bình giữ nhiệt", { timeout: 90_000 });

  const suggestions = page.getByTestId("shopee-suggestions");
  const products = suggestions.getByTestId("suggested-product");
  // One idea from the caption job, two products meeting the rules (the fake's third has 4.2 stars).
  await expect(products).toHaveCount(2, { timeout: 30_000 });
  const first = products.filter({ hasText: "bình giữ nhiệt loại 1" });
  await first.getByRole("button", { name: "Chọn" }).click();
  await expect(first.getByText("Đã chọn")).toBeVisible();
  await expect(page.getByTestId("article-preview-comment")).toContainText(
    "bình giữ nhiệt loại 1: link Shopee của Page",
  );
  await expect(page.getByTestId("article-preview")).toContainText("Link sản phẩm mình để ở bình luận ghim.");
});

test("an article's products show even when its page never saw the search pending", async ({ page }) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await addShopeeAccount(page);
  // The page reads the article every few seconds while the AI writes; the worker's search can start and finish
  // between two reads, so the article only ever says "idle". Hiding "pending" from the page makes that certain.
  await page.route(/\/api\/articles\/\d+$/, async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const response = await route.fetch();
    const article = await response.json();
    await route.fulfill({ response, json: { ...article, suggest: { ...article.suggest, state: "idle" } } });
  });

  await page.goto("/articles");
  await page.getByRole("button", { name: "Tạo bài viết" }).click();
  const drawer = page.getByRole("dialog", { name: "Tạo bài viết" });
  await drawer.getByLabel("Chủ đề của bài").fill("uống nước ấm buổi sáng");
  await drawer.getByRole("button", { name: "Tạo bài" }).click();
  await page.getByRole("button", { name: "AI viết" }).click();
  await expect(page.getByLabel("Gợi ý sản phẩm")).toHaveValue("bình giữ nhiệt", { timeout: 90_000 });
  await expect(page.getByTestId("shopee-suggestions").getByTestId("suggested-product")).toHaveCount(2, {
    timeout: 30_000,
  });
});
