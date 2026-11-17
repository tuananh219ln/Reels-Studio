/* The options page: paste, save or clear the second account's cookies (scan-account.js). */
const statusBox = document.getElementById("status");
const messageLine = document.getElementById("message");
const field = document.getElementById("cookies");

async function show() {
  const status = await scanAccountStatus();
  const parts = [];
  parts.push(
    status.userId
      ? `Đã lưu cookie tài khoản phụ (id ${status.userId}, lúc ${new Date(status.savedAt).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}).`
      : "Chưa lưu cookie tài khoản phụ: chưa quét được đối thủ.",
  );
  parts.push(
    status.incognito
      ? "Đã cho phép chạy ở chế độ ẩn danh."
      : "Chưa cho phép chạy ở chế độ ẩn danh (bước 1).",
  );
  statusBox.textContent = parts.join(" ");
  statusBox.className = `status ${status.userId && status.incognito ? "ok" : "warn"}`;
}

document.getElementById("save").addEventListener("click", async () => {
  try {
    const { userId } = await saveScanAccount(field.value);
    field.value = "";
    messageLine.textContent = `Đã lưu cookie của tài khoản ${userId}.`;
  } catch (error) {
    messageLine.textContent = error.message;
  }
  await show();
});

document.getElementById("clear").addEventListener("click", async () => {
  await clearScanAccount();
  messageLine.textContent = "Đã xóa cookie tài khoản phụ khỏi Chrome này.";
  await show();
});

show();
