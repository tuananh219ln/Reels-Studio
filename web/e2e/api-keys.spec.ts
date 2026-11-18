import { expect, test } from "@playwright/test";
import { loginAsSeed, resetDatabase } from "./helpers";

test.beforeEach(() => resetDatabase());

test("team backup narration keys sit under each main key, are reordered and removed, and logged by their last characters", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await loginAsSeed(page);
  await page.goto("/settings/ai");
  const backups = page.getByTestId("key-list-elevenlabs");
  const rows = backups.getByTestId("key-row");
  await backups.getByLabel("Dán key ElevenLabs").fill("fake-elevenlabs-key-backup-CCCC");
  await backups.getByRole("button", { name: "Thêm key" }).click();
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Key dự phòng 1");
  await expect(rows.first()).toContainText("…CCCC");

  await backups.getByLabel("Tên key ElevenLabs mới").fill("Tài khoản phụ");
  await backups.getByLabel("Dán key ElevenLabs").fill("fake-elevenlabs-key-backup-DDDD");
  await backups.getByRole("button", { name: "Thêm key" }).click();
  await expect(rows).toHaveCount(2);
  await backups.getByRole("button", { name: "Đưa Tài khoản phụ lên" }).click();
  await expect(rows.first()).toContainText("…DDDD");
  await expect(page.getByText("fake-elevenlabs-key-backup")).toHaveCount(0);

  // Gemini and VieNeu keep their own backups in the same group.
  await expect(page.getByTestId("key-list-gemini")).toBeVisible();
  await expect(page.getByTestId("key-list-vieneu")).toBeVisible();

  await backups.getByRole("button", { name: "Xoá Key dự phòng 1" }).click();
  await page.getByRole("tooltip").getByRole("button", { name: "Xoá", exact: true }).click();
  await expect(rows).toHaveCount(1);

  await page.getByTestId("history-images").getByRole("button", { name: "Lịch sử" }).click();
  const history = page.getByRole("dialog", { name: "Lịch sử: Ảnh AI và giọng đọc" });
  await expect(history).toContainText("Key dự phòng (ElevenLabs): (trống) → Key dự phòng 1 …CCCC");
  await expect(history).not.toContainText("fake-elevenlabs-key-backup");
});
