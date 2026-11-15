import { expect, test, type Page } from "@playwright/test";
import { loginAsSeed, resetDatabase, sideTab } from "./helpers";

// The video page's layout chosen by each member: the header folded to one row, and the line between the scenes and
// the side panel dragged (docs/decisions/2026-11-15-video-page-fold-and-split.md).
test.beforeEach(() => resetDatabase());

/** A new video with its script and no photos yet, so each of its six scenes blocks the render. */
async function videoWithScript(page: Page) {
  await loginAsSeed(page);
  await page.getByRole("button", { name: "Tạo video" }).click();
  const dialog = page.getByRole("dialog", { name: "Tạo video" });
  await dialog.getByLabel("Chủ đề", { exact: true }).fill("xương khớp sau 50 tuổi");
  await dialog.getByRole("button", { name: "Viết kịch bản" }).click();
  await expect(page.getByTestId("scene")).toHaveCount(5, { timeout: 90_000 });
  await expect(page.getByTestId("job-status")).toHaveCount(0, { timeout: 90_000 });
}

/** Drags the line between the columns to `x` px from the window's left. */
async function dragLineTo(page: Page, x: number) {
  const handle = (await page.getByTestId("split-handle").boundingBox())!;
  await page.mouse.move(handle.x + handle.width / 2, handle.y + 200);
  await page.mouse.down();
  await page.mouse.move(x, handle.y + 200, { steps: 8 });
  await page.mouse.up();
}

test("the header folds to one row, keeps a word on what needs a look, and stays folded after a reload", async ({
  page,
}) => {
  test.setTimeout(150_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await videoWithScript(page);
  const bar = page.getByTestId("render-bar");
  await expect(bar.getByTestId("video-progress")).toBeVisible();
  await expect(bar.getByTestId("folded-status")).toHaveCount(0);

  await bar.getByRole("button", { name: "Thu gọn đầu trang" }).click();
  await expect(bar.getByTestId("header-details")).toBeHidden();
  // The six blocked scenes are still said beside the title.
  await expect(bar.getByTestId("folded-status")).toHaveText(/Còn 6 lỗi cần sửa/);

  await page.reload();
  await expect(page.getByTestId("render-bar").getByTestId("header-details")).toBeHidden();
  // The word unfolds the header.
  await page.getByTestId("folded-status").click();
  await expect(bar.getByTestId("video-progress")).toBeVisible();
  await expect(bar.getByRole("button", { name: "Thu gọn đầu trang" })).toBeVisible();
});

test("the line between the scenes and the panel is dragged, kept, held to each side's minimum, and reset", async ({
  page,
}) => {
  test.setTimeout(150_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await videoWithScript(page);
  const split = page.getByTestId("split-columns");
  const panel = page.locator("[data-side-panel]");
  const scenes = page.getByTestId("editor-column");
  await expect(split).toHaveAttribute("data-share", "0.600");

  // Dragged to the left: the panel gets wider, and that stays after a reload.
  await dragLineTo(page, 600);
  const share = Number(await split.getAttribute("data-share"));
  expect(share).toBeLessThan(0.45);
  await page.reload();
  await expect(page.getByTestId("split-columns")).toHaveAttribute("data-share", share.toFixed(3));

  // A wide panel: the blocks of "Bình luận & Sản phẩm" side by side.
  await sideTab(page, "Bình luận & Sản phẩm");
  await expect(async () => {
    const comments = (await panel.locator('[data-post-block="comments"]').boundingBox())!;
    const products = (await panel.locator('[data-post-block="products"]').boundingBox())!;
    expect(Math.abs(comments.y - products.y)).toBeLessThan(2);
    expect(products.x).toBeGreaterThan(comments.x + comments.width - 1);
  }).toPass();

  // As far left as it goes: the scenes keep 420 px.
  await dragLineTo(page, 0);
  expect((await scenes.boundingBox())!.width).toBeGreaterThanOrEqual(419);
  // As far right as it goes: the panel keeps 440 px, its blocks back in one column.
  await dragLineTo(page, 1440);
  expect((await panel.boundingBox())!.width).toBeGreaterThanOrEqual(439);
  const comments = (await panel.locator('[data-post-block="comments"]').boundingBox())!;
  const products = (await panel.locator('[data-post-block="products"]').boundingBox())!;
  expect(products.y).toBeGreaterThan(comments.y + comments.height - 1);

  // A double click goes back to 60/40.
  await page.getByTestId("split-handle").dblclick();
  await expect(split).toHaveAttribute("data-share", "0.600");
});
