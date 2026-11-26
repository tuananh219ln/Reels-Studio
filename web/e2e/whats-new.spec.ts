import { expect, type Page, test } from "@playwright/test";
import {
  buildEntries,
  byDeploy,
  type Changelog,
  deployTimes,
  guidesFromFiles,
  guideUpdates,
  isRecent,
  type MergedPull,
  pagesFromFiles,
  requestedBy,
  withNames,
  summarize,
  telegramMessage,
  unseenEntries,
} from "../src/lib/changelog";
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

  test("a change links the in-app guides its PR added or changed", () => {
    expect(
      guidesFromFiles([
        { filename: "api/src/reels_api/guides/whats-new.md", status: "added" },
        { filename: "api/src/reels_api/guides/videos.md", status: "modified" },
        { filename: "api/src/reels_api/guides/old.md", status: "removed" },
        { filename: "docs/ux-guidelines.md", status: "modified" },
        { filename: "api/src/reels_api/guides.py", status: "modified" },
      ]),
    ).toEqual(["whats-new", "videos"]);
  });

  test("a change is by the member its PR was requested by, else its GitHub author", () => {
    const body = "<!-- x -->\n_Requested by **Nam dev** · [project thread](https://x)_\n\n## Làm gì và vì sao\n\nA.";
    expect(requestedBy(body)).toBe("Nam dev");
    expect(requestedBy("## Làm gì và vì sao\n\nA.")).toBe("");
    const [asked, plain, named] = buildEntries([
      { ...pull(3, "feat: ba", "2026-11-26T11:00:00Z", body), user: { login: "namtc07" } },
      { ...pull(2, "feat: hai", "2026-11-26T10:00:00Z"), user: { login: "tuananh219ln" } },
      { ...pull(1, "feat: một", "2026-11-26T09:00:00Z"), user: { login: "khongten" } },
    ]);
    expect(
      withNames([asked, plain, named], { tuananh219ln: "Tuấn Anh", namtc07: "Nam GitHub" }).map((e) => e.author),
    ).toEqual(["Nam dev", "Tuấn Anh", "khongten"]);
  });

  test("each guide knows the newest change that wrote it, new for a week", () => {
    const [newer, older] = buildEntries([
      pull(2, "feat: mới", "2026-11-26T09:00:00Z"),
      pull(1, "feat: cũ", "2026-11-10T09:00:00Z"),
    ]).map((entry) => ({ ...entry, guides: ["videos"] }));
    const updates = guideUpdates([older, { ...newer, guides: ["videos", "affiliate"] }]);
    expect(updates.videos.number).toBe(2);
    expect(updates.affiliate.number).toBe(2);
    expect(isRecent(updates.videos, Date.parse("2026-11-30T09:00:00Z"))).toBe(true);
    expect(isRecent(updates.videos, Date.parse("2026-12-04T09:00:00Z"))).toBe(false);
    expect(isRecent(undefined)).toBe(false);
  });

  test("Thử ngay is the screens a PR changed, none when it changed more than two", () => {
    const file = (filename: string, status = "modified") => ({ filename, status });
    expect(
      pagesFromFiles([
        file("web/src/app/(app)/videos/page.tsx"),
        file("web/src/app/(app)/videos/[id]/page.tsx"),
        file("web/src/app/(app)/posts/page.tsx"),
        file("web/src/app/(app)/layout.tsx"),
        file("web/src/components/AppShell.tsx"),
      ]),
    ).toEqual(["/videos", "/posts"]);
    expect(
      pagesFromFiles([
        file("web/src/app/(app)/videos/page.tsx"),
        file("web/src/app/(app)/posts/page.tsx"),
        file("web/src/app/(app)/stats/page.tsx"),
      ]),
    ).toEqual([]);
    expect(pagesFromFiles([file("web/src/app/(app)/calendar/page.tsx")])).toEqual([]);
  });

  test("changes are grouped by the deploy that brought them", () => {
    const entries = buildEntries([
      pull(3, "feat: ba", "2026-11-26T11:00:00Z"),
      pull(2, "feat: hai", "2026-11-26T09:01:00Z"),
      pull(1, "fix: một", "2026-11-26T09:00:00Z"),
    ]);
    const runs = [
      // Its own run failed, so #1 went live with #2's; #3 is in the deploy running now.
      { created_at: "2026-11-26T09:01:03Z", updated_at: "2026-11-26T09:20:00Z" },
      { created_at: "2026-11-25T08:00:00Z", updated_at: "2026-11-25T08:20:00Z" },
    ];
    const timed = deployTimes(entries, runs, "2026-11-26T11:05:00Z");
    expect(byDeploy(timed).map((group) => [group.deployed_at, group.entries.map((entry) => entry.number)])).toEqual([
      ["2026-11-26T11:05:00Z", [3]],
      ["2026-11-26T09:20:00Z", [2, 1]],
    ]);
  });

  test("the Telegram message lists what this deploy brought, and nothing for a deploy without changes", () => {
    const entries = deployTimes(
      buildEntries([
        pull(2, "feat: Đăng <nhanh> hơn", "2026-11-26T11:00:00Z", "## Làm gì và vì sao\n\nMột bước & xong."),
        pull(1, "fix: cũ", "2026-11-20T09:00:00Z"),
      ]),
      [{ created_at: "2026-11-20T09:00:01Z", updated_at: "2026-11-20T09:20:00Z" }],
      "2026-11-26T11:05:00Z",
    );
    const file = { version: "x", generated_at: "2026-11-26T11:05:00Z", entries };
    expect(telegramMessage(file, "https://reels.vn/")).toBe(
      [
        "<b>Reels Studio vừa cập nhật</b>",
        "",
        "• <b>Đăng &lt;nhanh&gt; hơn</b> (Tính năng mới)",
        "Một bước &amp; xong.",
        "",
        '<a href="https://reels.vn/whats-new">Xem trong app</a>',
      ].join("\n"),
    );
    expect(telegramMessage({ ...file, generated_at: "2026-11-27T00:00:00Z" })).toBeNull();
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
  function withGuide(file: Changelog, number: number, slug: string): Changelog {
    return {
      ...file,
      entries: file.entries.map((entry) =>
        entry.number === number
          ? { ...entry, guides: [slug], pages: ["/posts"], deployed_at: hoursAgo(0.5), author: "Nam dev" }
          : entry,
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

  test("the Có gì mới page lists every change, counts as seen and opens a change's guide", async ({ page }) => {
    const file = withGuide(
      changelog([
        [21, "feat(web): thông báo có gì mới", hoursAgo(1)],
        [20, "fix: sửa lỗi cũ", hoursAgo(24 * 10)],
      ]),
      21,
      "whats-new",
    );
    await serve(page, () => file);
    await loginAsSeed(page);

    // "Xem tất cả" in the window leads to the page; the window does not open again there.
    const dialog = page.getByRole("dialog", { name: "Có gì mới" });
    await dialog.getByRole("button", { name: "Xem tất cả" }).click();
    await expect(page).toHaveURL(/\/whats-new$/);
    await expect(dialog).toBeHidden();
    const entries = page.getByRole("main").getByTestId("whats-new-entry");
    await expect(entries).toHaveCount(2);
    // Grouped by deploy: the newer change under its own "Cập nhật", the one without a time apart.
    await expect(page.getByRole("main").getByTestId("whats-new-deploy")).toHaveCount(2);
    await expect(page.getByRole("main").getByTestId("whats-new-deploy").first()).toContainText("Cập nhật");
    await expect(entries.nth(0)).toContainText("bởi Nam dev");

    // The page's own guide, and a change's guide.
    await page.getByRole("button", { name: "Hướng dẫn" }).click();
    await expect(page.getByRole("heading", { name: "Hướng dẫn: Có gì mới" })).toBeVisible();
    await page.keyboard.press("Escape");
    await entries.nth(0).getByRole("link", { name: "Xem hướng dẫn" }).click();
    await expect(page).toHaveURL(/\/guides\?guide=whats-new/);
    await expect(page.getByRole("heading", { name: "Hướng dẫn: Có gì mới" })).toBeVisible();
    await page.goto("/whats-new");
    await entries.nth(0).getByRole("link", { name: "Thử ngay: Bài đăng" }).click();
    await expect(page).toHaveURL(/\/posts/);

    await page.goto("/videos");
    await expect(page.getByTestId("whats-new-bell")).toBeVisible();
    await expect(dialog).toBeHidden();
  });

  test("opening the page from the menu marks the new changes seen", async ({ page }) => {
    const file = changelog([[31, "feat: một thay đổi mới", hoursAgo(1)]]);
    await serve(page, () => file);
    await page.goto("/login");
    await loginAsSeed(page);
    await expect(page.getByRole("dialog", { name: "Có gì mới" })).toBeVisible();
    await page.goto("/whats-new");
    await expect(page.getByRole("dialog", { name: "Có gì mới" })).toBeHidden();
    await expect(page.getByRole("main").getByTestId("whats-new-entry").first()).toContainText("Mới");
    await expect.poll(async () => (await (await page.request.get("/api/me")).json()).changelog_seen_at).not.toBeNull();
    await page.goto("/videos");
    await expect(page.getByTestId("whats-new-bell")).toBeVisible();
    await expect(page.getByRole("dialog", { name: "Có gì mới" })).toBeHidden();
  });

  test("Tất cả hướng dẫn marks a guide a new change wrote, and names the change", async ({ page }) => {
    const file = withGuide(changelog([[41, "feat(affiliate): custom link nhanh hơn", hoursAgo(3)]]), 41, "custom-link");
    await serve(page, () => file);
    await loginAsSeed(page);
    await page.getByRole("dialog", { name: "Có gì mới" }).getByRole("button", { name: "Đã xem" }).click();
    await page.goto("/guides?guide=custom-link");
    const menu = page.getByTestId("guides-menu");
    await expect(menu.getByRole("menuitem", { name: /Custom Link/ })).toContainText("Mới");
    await expect(menu.getByRole("menuitem", { name: /màn Affiliate/ })).not.toContainText("Mới");
    await expect(page.getByTestId("guide-updated")).toContainText("Cập nhật cùng Custom link nhanh hơn");
    await page.getByTestId("guide-updated").getByRole("link").click();
    await expect(page).toHaveURL(/\/whats-new$/);
  });

  test("with no changelog (development, E2E) there is no bell and no window", async ({ page }) => {
    await page.route(/\/changelog\.json/, (route) => route.fulfill({ status: 404, body: "" }));
    await loginAsSeed(page);
    await expect(page.getByTestId("header-name")).toBeVisible();
    await expect(page.getByTestId("whats-new-bell")).toHaveCount(0);
    await expect(page.getByRole("dialog", { name: "Có gì mới" })).toBeHidden();
  });
});
