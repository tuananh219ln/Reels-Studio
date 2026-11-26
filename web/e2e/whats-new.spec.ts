import { expect, type Page, test } from "@playwright/test";
import { buildEntries, type Changelog, type MergedPull, summarize, unseenEntries } from "../src/lib/changelog";
import { loginAsSeed, resetDatabase } from "./helpers";

// "Có gì mới" (docs/decisions/2026-11-26-whats-new.md): the deploy writes changelog.json from the merged PRs.

const pull = (number: number, title: string, mergedAt: string | null, body: string | null = null): MergedPull => ({
  number,
  title,
  body,
  merged_at: mergedAt,
  html_url: `https://github.com/o/r/pull/${number}`,
});

test.describe("the changelog read from merged PRs", () => {
  test("keeps feat, fix and perf PRs, newest first, and leaves the rest out", () => {
    const entries = buildEntries([
      pull(1, "feat(video): mP4 tải lên", "2026-11-26T09:00:00Z"),
      pull(2, "chore(ci): cache pip", "2026-11-26T10:00:00Z"),
      pull(3, "fix: bỏ tiếng ting", "2026-11-26T11:00:00Z"),
      pull(4, "docs: sửa README", "2026-11-26T12:00:00Z"),
      pull(5, "feat(api): chưa merge", null),
      pull(6, "perf(render)!: dựng nhanh hơn", "2026-11-25T08:00:00Z"),
      pull(7, "Merge main into feature/x", "2026-11-26T13:00:00Z"),
    ]);
    expect(entries.map((entry) => [entry.number, entry.kind, entry.title])).toEqual([
      [3, "fix", "Bỏ tiếng ting"],
      [1, "feature", "MP4 tải lên"],
      [6, "improvement", "Dựng nhanh hơn"],
    ]);
  });

  test("the detail is the first paragraph of 'Làm gì và vì sao', as plain text", () => {
    const body = [
      "<!-- claude-projects-attribution: {} -->",
      "_Requested by **Nam dev** · [project thread](https://x)_",
      "",
      "## Làm gì và vì sao",
      "",
      "Thêm **Nền tối mờ** sau chữ, bật ở `text_shade` (xem [quyết định](https://x)).",
      "",
      "- Chi tiết kỹ thuật",
      "",
      "## Đã kiểm tra thế nào",
      "Chạy test.",
    ].join("\n");
    expect(summarize(body)).toBe("Thêm Nền tối mờ sau chữ, bật ở text_shade (xem quyết định).");
    expect(summarize("## Làm gì và vì sao\n\nBa việc cùng một PR, theo yêu cầu:\n\n1. Một")).toBe("");
    expect(summarize(null)).toBe("");
    const long = summarize(`## Làm gì và vì sao\n\n${"chữ ".repeat(200)}`);
    expect(long.length).toBeLessThanOrEqual(281);
    expect(long.endsWith("…")).toBe(true);
  });

  test("new changes are those merged after the member's mark, or in the last three days without one", () => {
    const now = Date.parse("2026-11-26T12:00:00Z");
    const entries = buildEntries([
      pull(1, "feat: mới", "2026-11-26T09:00:00Z"),
      pull(2, "feat: hôm qua", "2026-11-25T09:00:00Z"),
      pull(3, "feat: tuần trước", "2026-11-19T09:00:00Z"),
    ]);
    expect(unseenEntries(entries, "2026-11-25T09:00:00Z", now).map((entry) => entry.number)).toEqual([1]);
    expect(unseenEntries(entries, null, now).map((entry) => entry.number)).toEqual([1, 2]);
  });
});

test.describe("Có gì mới in the app", () => {
  test.beforeEach(() => resetDatabase());

  const hoursAgo = (hours: number) => new Date(Date.now() - hours * 3600_000).toISOString();
  function changelog(entries: [number, string, string][]): Changelog {
    return {
      version: "test",
      generated_at: new Date().toISOString(),
      entries: buildEntries(
        entries.map(([number, title, at]) => pull(number, title, at, `## Làm gì và vì sao\n\n${title}.`)),
      ),
    };
  }
  async function serve(page: Page, file: () => Changelog) {
    await page.route(/\/changelog\.json/, (route) => route.fulfill({ json: file() }));
  }

  test("opens once with what is new, then the bell keeps the history", async ({ page }) => {
    let file = changelog([
      [11, "feat(video): thêm thông báo tính năng mới", hoursAgo(2)],
      [10, "fix: sửa lỗi cũ", hoursAgo(24 * 10)],
    ]);
    await serve(page, () => file);
    await loginAsSeed(page);

    const dialog = page.getByRole("dialog", { name: "Có gì mới" });
    await expect(dialog).toBeVisible();
    const entries = dialog.getByTestId("whats-new-entry");
    await expect(entries).toHaveCount(2);
    await expect(entries.nth(0)).toContainText("Thêm thông báo tính năng mới");
    await expect(entries.nth(0)).toContainText("Mới");
    await expect(entries.nth(0)).toContainText("Tính năng mới");
    await expect(entries.nth(1)).toContainText("Sửa lỗi cũ");
    await expect(entries.nth(1)).not.toContainText("Mới");
    await dialog.getByRole("button", { name: "Đã xem" }).click();
    await expect(dialog).toBeHidden();

    // Seen is kept on the account: a reload does not open it again, and the bell shows the history.
    await page.reload();
    await expect(page.getByTestId("whats-new-bell")).toBeVisible();
    await expect(dialog).toBeHidden();
    await page.getByTestId("whats-new-bell").click();
    await expect(dialog.getByTestId("whats-new-entry")).toHaveCount(2);
    await expect(dialog.getByText("Mới", { exact: true })).toHaveCount(0);
    await dialog.getByRole("button", { name: "Đã xem" }).click();

    // A deploy goes live while the tab is open: the tab asks to reload, and after it the new change opens.
    file = changelog([
      [12, "feat(posts): đăng nhanh hơn", hoursAgo(0.1)],
      [11, "feat(video): thêm thông báo tính năng mới", hoursAgo(2)],
      [10, "fix: sửa lỗi cũ", hoursAgo(24 * 10)],
    ]);
    await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
    const bar = page.getByTestId("new-version-bar");
    await expect(bar).toContainText("Đã có bản mới");
    await bar.getByRole("button", { name: "Tải lại" }).click();
    await expect(dialog).toBeVisible();
    await expect(dialog.getByTestId("whats-new-entry").first()).toContainText("Đăng nhanh hơn");
    await expect(page.getByTestId("new-version-bar")).toBeHidden();
  });

  test("with no changelog (development, E2E) there is no bell and no window", async ({ page }) => {
    await page.route(/\/changelog\.json/, (route) => route.fulfill({ status: 404, body: "" }));
    await loginAsSeed(page);
    await expect(page.getByTestId("header-name")).toBeVisible();
    await expect(page.getByTestId("whats-new-bell")).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "Có gì mới" })).toHaveCount(0);
  });
});
