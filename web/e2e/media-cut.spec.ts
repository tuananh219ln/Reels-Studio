// "Cắt thành file mới" in the Kho tư liệu: a part of a clip saved as a new tagged item, the clip itself kept
// (docs/decisions/2026-11-16-trim-clip-to-library.md). FFmpeg runs in the api, as for any clip.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { loginAsSeed, resetDatabase } from "./helpers";

test.beforeEach(() => resetDatabase());

/** An 8-second upright clip, long enough to cut a part from. */
function makeClip(): Buffer {
  const file = path.join(os.tmpdir(), `e2e-cut-${process.pid}.mp4`);
  execFileSync("ffmpeg", [
    "-v",
    "error",
    "-y",
    "-f",
    "lavfi",
    "-i",
    "testsrc2=size=720x1280:rate=25:duration=8",
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    file,
  ]);
  return readFileSync(file);
}

test("Kho tư liệu: a clip's part is cut into a new tagged item and the clip stays", async ({ page }) => {
  test.setTimeout(120_000);
  await loginAsSeed(page);
  const headers = { Origin: new URL(page.url()).origin };
  const made = await page.request.post("/api/media", {
    multipart: { file: { name: "bep.mp4", mimeType: "video/mp4", buffer: makeClip() }, folder: "Tải về" },
    headers,
  });
  expect(made.status()).toBe(201);

  await page.goto("/media?view=grid");
  await page.getByTestId("media-item").filter({ hasText: "bep.mp4" }).locator("img").first().click();
  await page.getByRole("dialog", { name: "bep.mp4" }).getByRole("button", { name: "Cắt thành file mới" }).click();
  const cut = page.getByRole("dialog", { name: "Cắt “bep.mp4” thành file mới" });
  const save = cut.getByRole("button", { name: "Cắt và lưu vào kho" });

  // Past the clip's end, and untagged, it cannot be saved.
  await cut.getByLabel("Giây bắt đầu").fill("2");
  await cut.getByLabel("Độ dài đoạn cắt").fill("7");
  await expect(cut.getByText("vượt quá độ dài clip")).toBeVisible();
  await cut.getByLabel("Độ dài đoạn cắt").fill("3");
  await expect(cut.getByText("Lấy đoạn 2–5 giây")).toBeVisible();
  await expect(save).toBeDisabled();
  await cut.getByLabel("Thẻ của đoạn cắt").fill("Cảnh 1 Bếp");
  await cut.getByLabel("Thẻ của đoạn cắt").press("Enter");
  // The suggestions close when the dialog's title is clicked, uncovering its buttons.
  await cut.locator(".ant-modal-title").click();
  await expect(page.locator(".ant-select-dropdown:visible")).toHaveCount(0);
  await save.click();
  await expect(page.getByText("Đã lưu “bep.mp4 (2–5s)” vào kho")).toBeVisible();

  // Both are in the library: the cut with its tag and about three seconds, the clip as it was.
  await expect(page.getByTestId("media-item")).toHaveCount(2);
  const items = (await (await page.request.get("/api/media")).json()).items as {
    name: string;
    tags: string[];
    seconds: number;
    folder: string;
  }[];
  const part = items.find((item) => item.name === "bep.mp4 (2–5s)")!;
  expect(part.tags).toEqual(["canh-1-bep"]);
  expect(part.folder).toBe("Tải về");
  expect(Math.abs(part.seconds - 3)).toBeLessThan(0.3);
  expect(items.some((item) => item.name === "bep.mp4")).toBe(true);
});
