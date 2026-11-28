import { expect, test, type Page } from "@playwright/test";
import {
  addUser,
  chooseOption,
  connectFacebook,
  importExportItem,
  login,
  loginAsSeed,
  openPanel,
  resetDatabase,
} from "./helpers";

// Issue #47. Shopee is the fake one (api/scripts/fake_services.py), which knows this App ID and Secret.
const APP_ID = "1000001";
const SECRET = "fake-shopee-secret";

test.beforeEach(() => resetDatabase());

async function addShopeeAccount(page: Page) {
  await page.goto("/settings/affiliate-accounts");
  await page.getByRole("button", { name: "Thêm kết nối" }).click();
  await page.getByRole("menuitem", { name: "Thêm tài khoản" }).click();
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
  await page.getByRole("menuitem", { name: "Quản lý kênh" }).click();
  const owner = page.getByTestId("fanpage-card").getByTestId("fanpage-owner");
  await expect(owner).toContainText("Thuộc: bạn");
  await expect(owner).toContainText("Shopee: dùng link dán tay");
  await page.getByRole("button", { name: "Cài đặt Trang Dưỡng Sinh" }).click();
  const settings = page.getByRole("dialog", { name: /Tài khoản và chủ Page/ });
  await chooseOption(page, settings.getByLabel("Tài khoản Shopee của Trang Dưỡng Sinh"), "Shopee: Shopee của An");
  await expect(settings.getByLabel("Tài khoản Shopee của Trang Dưỡng Sinh")).toBeVisible();
  await expect(owner).toContainText("Shopee: Shopee của An");
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
  await expect(binh.getByText("Chưa có tài khoản Shopee nào")).toBeVisible();
  await binh.goto("/fanpages");
  // A teammate sees whose Page it is and what is public about it, never the owner's Shopee or TikTok account.
  const theirs = binh.getByTestId("fanpage-owner");
  await expect(theirs).toContainText("Thuộc: Nguyễn Văn An");
  await expect(theirs).not.toContainText("Shopee");
  await expect(theirs).not.toContainText("TikTok");
  await expect(theirs.getByRole("button", { name: /^Cài đặt/ })).toHaveCount(0);
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

  await openPanel(page, "Sản phẩm Shopee");
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

test("without an App ID, an affiliate link pasted on the video can be chosen, and filled in by hand first", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  await page.goto("/videos");
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("xương khớp");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page.getByTestId("scene").first()).toBeVisible({ timeout: 90_000 });

  await openPanel(page, "Sản phẩm Shopee");
  const suggestions = page.getByTestId("shopee-suggestions");
  await suggestions.getByLabel("Dán link aff Shopee").fill("https://s.shopee.vn/4LKghKN3cR");
  await suggestions.getByRole("button", { name: "Thêm link" }).click();
  const pasted = suggestions.getByTestId("suggested-product");
  await expect(pasted).toContainText("Chưa có thông tin sản phẩm");
  // Stars and sales not being filled in does not block choosing it; they can still be filled in by hand.
  await expect(pasted.getByRole("button", { name: "Chọn" })).toHaveCount(1);

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

  // The rarer actions sit under "⋯".
  await page.getByRole("button", { name: "Thao tác khác với video" }).click();
  await page.getByRole("menuitem", { name: "Tạo bản TikTok" }).click();
  const clone = page.getByRole("dialog", { name: "Tạo bản TikTok" });
  await expect(clone.getByLabel("Yêu cầu đổi")).toHaveValue(/Viết lại cho TikTok/);
  await clone.getByRole("button", { name: "Tạo bản TikTok" }).click();
  await expect(page).not.toHaveURL(source);
  await expect(page.getByTestId("video-platform")).toHaveText("Bản TikTok");
  await expect(page.getByTestId("variants")).toContainText("Bản Facebook gốc:");
  // The TikTok version cannot make another TikTok version: "⋯" no longer offers it. Its script is still being
  // written for a moment (the menu then holds only what a script-less video has), so the look is retried as one step.
  await expect(async () => {
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Thao tác khác với video" }).click();
    await expect(page.getByRole("menuitem", { name: "Nhân bản y hệt" })).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 60_000 });
  await expect(page.getByRole("menuitem", { name: "Tạo bản TikTok" })).toHaveCount(0);
  await page.keyboard.press("Escape");

  // On the list the version sits on its source's card, not on a card of its own, and opens from there.
  await page.getByRole("link", { name: "Danh sách video" }).click();
  await expect(page.getByTestId("video-card")).toHaveCount(1);
  // Only a TikTok version is tagged with its platform; the Facebook source card shows where it is out instead.
  await expect(page.getByTestId("video-card").getByTestId("video-platform")).toHaveCount(0);
  await expect(page.getByTestId("video-card").getByTestId("posted-platforms")).toHaveCount(1);
  const version = page.getByTestId("video-version");
  await expect(version).toHaveText(/TikTok\s*Nháp/);
  await version.click();
  await expect(page.getByTestId("video-platform")).toHaveText("Bản TikTok");
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
  await page.getByRole("button", { name: "Thêm kết nối" }).click();
  await page.getByRole("menuitem", { name: "Kết nối TikTok" }).click();
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

test("a member's TikTok account: set on their Page, and shown there after a reload", async ({ page }) => {
  await loginAsSeed(page);
  // TikTok's consent page, answered as TikTok does once the member allows the app.
  await page.route("https://www.tiktok.com/**", (route) => {
    const asked = new URL(route.request().url());
    if (asked.pathname !== "/v2/auth/authorize/") {
      return route.abort();
    }
    const back = `/api/tiktok/oauth/callback?code=fake-tiktok-code&state=${asked.searchParams.get("state")}`;
    return route.fulfill({ status: 302, headers: { location: `http://localhost:3100${back}` } });
  });
  await page.goto("/settings/affiliate-accounts");
  await page.getByRole("button", { name: "Thêm kết nối" }).click();
  await page.getByRole("menuitem", { name: "Kết nối TikTok" }).click();
  await expect(page.getByText("Đã kết nối tài khoản TikTok")).toBeVisible();

  await connectFacebook(page);
  await page.getByRole("menuitem", { name: "Quản lý kênh" }).click();
  const owner = page.getByTestId("fanpage-card").getByTestId("fanpage-owner");
  await expect(owner).toContainText("Thuộc: bạn");
  await page.getByRole("button", { name: "Cài đặt Trang Dưỡng Sinh" }).click();
  const settings = page.getByRole("dialog", { name: /Tài khoản và chủ Page/ });
  await chooseOption(
    page,
    settings.getByLabel("Tài khoản TikTok của Trang Dưỡng Sinh"),
    "TikTok: An Lành SK (@anlanhsk)",
  );
  await page.reload();
  await expect(page.getByTestId("fanpage-owner")).toContainText("TikTok: An Lành SK");

  // The auto-post mode shows once an account is linked, starts on the draft, and "Đăng thẳng" stays after a reload.
  await expect(page.getByTestId("fanpage-owner")).toContainText("đẩy nháp đúng giờ");
  await page.getByRole("button", { name: "Cài đặt Trang Dưỡng Sinh" }).click();
  const modeDrawer = page.getByRole("dialog", { name: /Tài khoản và chủ Page/ });
  const mode = modeDrawer.getByLabel("Tự đăng TikTok của Trang Dưỡng Sinh");
  await chooseOption(page, mode, "Tự đăng TikTok: đăng thẳng công khai");
  await page.reload();
  await expect(page.getByTestId("fanpage-owner")).toContainText("đăng thẳng công khai");
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
  // The page keeps polling: a read still inside the route when the test ends failed the NEXT test with
  // "route.fetch: Test ended" (CI run 42369438965). Remove the route and let such a read be dropped quietly.
  await page.unrouteAll({ behavior: "ignoreErrors" });
});

test("Video đã đăng starts on the member's own and says whose commission each product earns", async ({ page }) => {
  await loginAsSeed(page);
  const me = (await (await page.request.get("/api/me")).json()) as { id: number };
  const post = (name: string, ownerId: number, owner: string, links = "missing") => ({
    platform: "facebook",
    fanpage_id: ownerId,
    name,
    fanpage_name: name,
    owner_id: ownerId,
    owner_name: owner,
    has_shopee_account: false,
    comment: "off",
    comment_error: null,
    links,
  });
  const video = (id: number, title: string, mine: boolean, posts: object[], products: object[]) => ({
    id,
    title,
    platform: "facebook",
    reel_url: null,
    published_at: "2026-11-09T01:00:00+00:00",
    suggestions: [],
    pinned_comment: "",
    mine,
    thumbnail_url: null,
    manual_comment: false,
    posts,
    products,
  });
  // A posted reel needs a render and Facebook's whole flow; the api's side is covered by test_affiliate_ownership.py.
  const rows = () => [
    video(
      1,
      "Trà gừng cho người trên 50",
      true,
      [post("Trang Dưỡng Sinh", me.id, "Nguyễn Văn An")],
      [
        {
          id: 7,
          name: "Gối cao su",
          url: "https://s.shopee.vn/cua-binh",
          status: "approved",
          problems: [],
          created_by_id: me.id + 1,
          created_by: "Trần Bình",
          has_saved_link: true,
          commission: [
            {
              fanpage_id: me.id,
              fanpage_name: "Trang Dưỡng Sinh",
              kind: "saved_link",
              user_id: me.id + 1,
              user_name: "Trần Bình",
            },
          ],
        },
        {
          id: 8,
          name: "Nồi hầm",
          url: null,
          status: "approved",
          problems: [],
          created_by_id: me.id,
          created_by: "Nguyễn Văn An",
          has_saved_link: false,
          commission: [
            {
              fanpage_id: me.id,
              fanpage_name: "Trang Dưỡng Sinh",
              kind: "no_link",
              user_id: null,
              user_name: null,
            },
          ],
        },
      ],
    ),
    video(2, "Bài của đồng đội", false, [post("Trang Bình", me.id + 1, "Trần Bình", "yes")], []),
  ];
  await page.route("**/api/affiliate-products/videos", (route) => route.fulfill({ json: rows() }));
  // "Đã dán link tay" answers with the video marked, as the api does.
  await page.route("**/api/affiliate-products/videos/1/manual", async (route) => {
    const { manual } = route.request().postDataJSON() as { manual: boolean };
    await route.fulfill({ json: { ...rows()[0], manual_comment: manual } });
  });
  await page.goto("/affiliate");
  const mine = page.getByRole("row", { name: /Trà gừng cho người trên 50/ });
  await expect(mine.getByTestId("video-post")).toHaveText("Trang Dưỡng Sinh");
  const notes = mine.getByTestId("commission-note");
  await expect(notes).toHaveText([
    "Gối cao su → hoa hồng về Trần Bình (link lưu sẵn)",
    "Nồi hầm → không có trong bình luận (chưa có link)",
  ]);
  await expect(page.getByRole("row", { name: /Bài của đồng đội/ })).toHaveCount(0);

  // The Page commented without a link: the row and the Page's dot say so, and "Thiếu link" lists it.
  await expect(mine.getByTestId("comment-status")).toHaveText("Đã bình luận, thiếu link");
  await expect(mine.getByTestId("link-dot")).toHaveAttribute("data-links", "missing");
  const linked = page.getByLabel("Lọc theo sản phẩm đã gắn");
  await linked.getByText("Thiếu link (1)").click();
  await expect(mine).toBeVisible();
  await expect(mine.getByRole("button", { name: "Thêm link" })).toBeVisible();

  // Pasted by hand (⋯): the comment is the member's, and the video moves to its own tab.
  await expect(async () => {
    await mine.getByRole("button", { name: "Thêm thao tác bình luận: Trà gừng cho người trên 50" }).click();
    await page.getByRole("menuitem", { name: "Đã dán link tay" }).click({ timeout: 2_000 });
  }).toPass();
  await expect(mine.getByTestId("comment-status")).toHaveText("Dán tay · đã bình luận, thiếu link");
  await linked.getByText("Dán tay (1)").click();
  await expect(mine).toBeVisible();
  await linked.getByText("Tất cả (1)").click();

  // The same videos as cards, then as a list beside the open one.
  const views = page.getByLabel("Kiểu hiển thị");
  await views.getByTitle("Dạng thẻ").click();
  await expect(page.getByTestId("video-card")).toHaveCount(1);
  await expect(page.getByTestId("video-card").getByTestId("commission-note")).toHaveCount(2);
  await views.getByTitle("Danh sách và chi tiết").click();
  await expect(page.getByTestId("video-detail")).toContainText("Trà gừng cho người trên 50");
  await views.getByTitle("Dạng bảng").click();

  await page.getByLabel("Của ai").getByText("Cả đội (2)").click();
  const theirs = page.getByRole("row", { name: /Bài của đồng đội/ });
  await expect(theirs.getByTestId("video-post")).toHaveText("Trang Bình (Trần Bình)");
  await expect(theirs.getByTestId("comment-status")).toHaveText("Có link");
  await expect(theirs.getByRole("button", { name: "Xem bình luận" })).toBeVisible();
});

test("Sản phẩm: my groups first, who added each product, and stars or sales fixed on the row", async ({ page }) => {
  await loginAsSeed(page);
  await connectFacebook(page);
  await page.getByRole("menuitem", { name: "Quản lý kênh" }).click();
  await page.getByRole("link", { name: "Trang Dưỡng Sinh" }).click();
  await page.getByRole("tab", { name: "Lịch đăng" }).click();
  const card = page.getByRole("tabpanel", { name: "Lịch đăng" }).getByTestId("page-queue");
  await chooseOption(page, card.getByLabel("Nhóm chủ đề của Trang Dưỡng Sinh"), "Sức khỏe");
  await expect(card).toContainText("Theo giờ đăng của nhóm chủ đề");

  await page.goto("/affiliate");
  await page.getByRole("tab", { name: "Sản phẩm" }).click();
  // My groups first, each with the Pages that post it.
  await page.getByLabel("Lọc theo nhóm").click();
  const groups = page.locator(".ant-select-dropdown:visible");
  await expect(groups).toContainText("Nhóm của tôi");
  await expect(groups.locator(".ant-select-item-option", { hasText: "Sức khỏe" })).toContainText("Trang Dưỡng Sinh");
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "Thêm sản phẩm" }).click();
  const adding = page.getByRole("dialog", { name: "Thêm sản phẩm" });
  await adding.getByRole("button", { name: "Nhập tay" }).click();
  await expect(adding).toBeHidden();
  const dialog = page.getByRole("dialog", { name: "Nhập tay sản phẩm" });
  await chooseOption(page, dialog.getByLabel("Nhóm chủ đề"), "Sức khỏe");
  await dialog.getByLabel("Tên sản phẩm").fill("Vừng đen rang");
  await dialog.getByLabel("Link affiliate").fill("https://s.shopee.vn/abc");
  await dialog.getByLabel("Tên shop").fill("Nhà Vừng");
  await chooseOption(page, dialog.getByLabel("Loại shop"), "Shopee Mall");
  await dialog.getByLabel("Số sao").fill("4.8");
  await dialog.getByLabel("Lượt bán").fill("50");
  await dialog.getByLabel("Giá (đ)").fill("100000");
  await dialog.getByLabel("Hoa hồng (%)").fill("10");
  await dialog.getByRole("button", { name: "Thêm" }).click();

  const product = page.getByRole("row", { name: /Vừng đen rang/ });
  await expect(product).toContainText("Người thêm: bạn");
  await expect(product).toContainText("Lượt bán dưới 100");
  const quick = product.getByTestId("quick-fill");
  await expect(quick.getByLabel("Số sao của Vừng đen rang")).toHaveValue("4.8");
  await quick.getByLabel("Lượt bán của Vừng đen rang").fill("500");
  await quick.getByRole("button", { name: "Lưu" }).click();
  await expect(product).toContainText("4.8 / 500");
  await expect(product.getByTestId("quick-fill")).toHaveCount(0);
  await product.getByRole("button", { name: "Duyệt" }).click();
  await expect(product).toContainText("Đã duyệt");
});

test("Nhập file: a preview first, and a teammate's product is added again with my link, theirs untouched", async ({
  page,
  browser,
}) => {
  await loginAsSeed(page);
  await addUser(page, "binh@doi.vn", "Trần Bình", "mat-khau-tam-1");
  const binh = await (await browser.newContext({ baseURL: "http://localhost:3100", locale: "vi-VN" })).newPage();
  await login(binh, "binh@doi.vn", "mat-khau-tam-1");
  await binh.getByLabel("Mật khẩu mới", { exact: true }).fill("binh-moi-1234");
  await binh.getByLabel("Nhập lại mật khẩu mới").fill("binh-moi-1234");
  await binh.getByRole("button", { name: "Lưu mật khẩu mới" }).click();
  await expect(binh).toHaveURL(/\/videos$/);
  const header =
    "Mã sản phẩm,Tên sản phẩm,Giá,Doanh thu,Tên cửa hàng,Tỉ lệ hoa hồng,Hoa hồng,Link sản phẩm,Link ưu đãi\n";
  const row = (id: number, name: string, link: string) =>
    `${id},${name},"45,0k",0,Shop,"2,5%",₫900,https://shopee.vn/product/1/${id},${link}\n`;
  // Through the browser's fetch, so the request carries the Origin the CSRF guard wants.
  await binh.evaluate(
    async (text) => {
      const { topics } = await fetch("/api/affiliate-products/options").then((response) => response.json());
      await fetch("/api/affiliate-products/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ knowledge_topic_id: topics[0].id, text }),
      });
    },
    header + row(21, "Gối của Bình", "https://s.shopee.vn/binh"),
  );

  await page.goto("/affiliate");
  await page.getByRole("tab", { name: "Sản phẩm" }).click();
  await importExportItem(page, /Nhập file/);
  const dialog = page.getByRole("dialog", { name: "Thêm sản phẩm" });
  await chooseOption(page, dialog.getByLabel("Nhóm chủ đề"), "Sức khỏe");
  await dialog.locator('input[type="file"]').setInputFiles({
    name: "lay-link-hang-loat.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      header + row(21, "Gối của Bình", "https://s.shopee.vn/an") + row(22, "Nồi của An", "https://s.shopee.vn/an-2"),
    ),
  });
  const preview = dialog.getByTestId("import-preview");
  await expect(preview).toContainText("Mới 1");
  await expect(preview).toContainText("Trùng người khác, tạo riêng 1");
  await expect(preview).toContainText("“Gối của Bình” Trần Bình đã thêm (nhóm Sức khỏe)");
  await dialog.getByRole("button", { name: "Nhập 2 sản phẩm" }).click();
  await expect(dialog.getByText("1 sản phẩm trùng với người khác được thêm riêng cho bạn")).toBeVisible();
  await dialog.getByRole("button", { name: "Huỷ" }).click();
  await expect(dialog).toBeHidden();
  const rows = page.getByRole("row", { name: /Gối của Bình/ });
  await expect(rows).toHaveCount(2);
  await expect(rows.filter({ hasText: "Người thêm: Trần Bình" })).toHaveCount(1);
  await expect(rows.filter({ hasText: "Người thêm: bạn" })).toHaveCount(1);
  await expect(page.getByRole("row", { name: /Nồi của An/ })).toContainText("Người thêm: bạn");
});

test("Tất cả hướng dẫn lists every screen's guides and reads one", async ({ page }) => {
  await loginAsSeed(page);
  await page.getByRole("menuitem", { name: "Tất cả hướng dẫn" }).click();
  await expect(page).toHaveURL(/\/guides/);
  const menu = page.getByTestId("guides-menu");
  for (const screen of ["Affiliate", "Video", "Kho kiến thức", "Thư viện nhạc", "Có gì mới", "Thông báo Telegram"]) {
    await expect(menu.locator(".ant-menu-item-group-title", { hasText: screen })).toBeVisible();
  }
  await expect(menu.getByRole("menuitem")).toHaveCount(8);
  await menu.getByText("gắn link affiliate hàng loạt").click();
  await expect(page.getByRole("heading", { name: /Custom Link của Shopee/ })).toBeVisible();
  await expect(page).toHaveURL(/[?&]guide=custom-link/);
});

test("Affiliate has a Hướng dẫn: the screen's guides open in a drawer, one at a time", async ({ page }) => {
  await loginAsSeed(page);
  await page.goto("/affiliate");
  await page.getByRole("button", { name: "Hướng dẫn" }).click();
  const drawer = page.getByRole("dialog", { name: "Hướng dẫn" });
  await expect(drawer.getByRole("heading", { name: "Hướng dẫn: màn Affiliate" })).toBeVisible();
  await drawer.getByText("gắn link affiliate hàng loạt").click();
  await expect(drawer.getByRole("heading", { name: /Custom Link của Shopee/ })).toBeVisible();
});

test("Nhập / Xuất has Shopee Custom Link's Excel file and its result import, once a group is open", async ({
  page,
}) => {
  await loginAsSeed(page);
  await page.goto("/affiliate");
  await page.getByRole("tab", { name: "Sản phẩm" }).click();

  // No group open: the Custom Link file is for one group, so both items wait for it.
  await page.getByRole("button", { name: /Nhập \/ Xuất/ }).click();
  await expect(page.getByRole("menuitem", { name: "Xuất file Custom Link (Excel)" })).toHaveAttribute(
    "aria-disabled",
    "true",
  );
  await expect(page.getByRole("menuitem", { name: "Nhập kết quả Shopee" })).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByRole("link", { name: "Xuất danh sách (CSV)" })).toBeVisible();
  await page.keyboard.press("Escape");

  await chooseOption(page, page.getByLabel("Lọc theo nhóm"), "Sức khỏe");
  await importExportItem(page, "Xuất file Custom Link (Excel)");
  const exporting = page.getByRole("dialog", { name: "Xuất file Custom Link" });
  await expect(exporting.getByRole("checkbox", { name: "Gồm cả món đã có link" })).toBeVisible();
  // The group has no Page yet, so the api says which Page the orders would go to is missing.
  await exporting.getByRole("button", { name: "Tải file Excel" }).click();
  await expect(page.getByText("Nhóm này chưa có Page nào đăng")).toBeVisible();
  // The footer's "Đóng" (the corner X is labelled "Đóng" too, but has no text); Escape needs focus in the dialog.
  await exporting.getByRole("button").filter({ hasText: "Đóng" }).click();
  await expect(exporting).toBeHidden();

  await importExportItem(page, "Nhập kết quả Shopee");
  await expect(page.getByRole("dialog", { name: "Nhập link đã chuyển đổi" })).toBeVisible();
});
