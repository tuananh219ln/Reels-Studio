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

test("a member's Shopee account: added, checked, set on their Page, and hidden from others", async ({ page }) => {
  await loginAsSeed(page);
  await addShopeeAccount(page);
  await page.getByRole("button", { name: "Kiểm tra kết nối" }).click();
  await expect(page.getByText("Shopee nhận App ID và Secret này")).toBeVisible();

  await connectFacebook(page);
  await page.getByRole("menuitem", { name: "Kết nối Fanpage" }).click();
  const owner = page.getByTestId("fanpage-card").getByTestId("fanpage-owner");
  await expect(owner).toContainText("Chủ: bạn");
  await chooseOption(page, owner.getByLabel("Tài khoản Shopee của Trang Dưỡng Sinh"), "Shopee: Shopee của An");
  await expect(owner.getByLabel("Tài khoản Shopee của Trang Dưỡng Sinh")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("fanpage-owner")).toContainText("Shopee: Shopee của An");

  await addUser(page, "binh@doi.vn", "Trần Bình", "mat-khau-tam-1");
  await login(page, "binh@doi.vn", "mat-khau-tam-1");
  await page.goto("/settings/affiliate-accounts");
  await expect(page.getByText("Chưa có tài khoản nào")).toBeVisible();
  await page.goto("/fanpages");
  await expect(page.getByTestId("fanpage-owner")).toHaveText("Chủ: Nguyễn Văn An");
  await page.goto("/affiliate");
  await page.getByRole("tab", { name: "Doanh thu" }).click();
  await expect(page.getByText("Chưa có tài khoản Shopee nào của bạn")).toBeVisible();
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

test("a TikTok version is its own video, linked both ways, with TikTok's posting kit", async ({ page }) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("tim mạch");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page.getByTestId("scene").first()).toBeVisible({ timeout: 90_000 });
  const source = page.url();

  await page.getByRole("button", { name: "Tạo bản TikTok" }).click();
  const clone = page.getByRole("dialog", { name: "Tạo bản TikTok" });
  await expect(clone.getByLabel("Yêu cầu đổi")).toHaveValue(/Viết lại cho TikTok/);
  await clone.getByRole("button", { name: "Tạo bản TikTok" }).click();
  await expect(page).not.toHaveURL(source);
  await expect(page.getByTestId("video-platform")).toHaveText("TikTok");
  await expect(page.getByTestId("variants")).toContainText("Bản TikTok của");
  await expect(page.getByRole("button", { name: "Tạo bản TikTok" })).toHaveCount(0);

  await page.getByRole("link", { name: "Danh sách video" }).click();
  await chooseOption(page, page.getByLabel("Lọc theo nền tảng"), "TikTok");
  await expect(page.getByTestId("video-platform")).toHaveCount(1);
});
