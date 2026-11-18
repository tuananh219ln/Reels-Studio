"use client";

import { Alert, Badge, Button, Flex, Popover, Typography } from "antd";
import { openExtensionOptions, type ScanAccount } from "@/lib/competitorScanner";

export type ScannerState = "ready" | "busy" | "offline";

/** The extension as one chip: green when it can scan, yellow while it scans, red when it cannot. */
export function ScannerChip({
  state,
  account,
  scanning,
}: {
  state: ScannerState;
  account: ScanAccount | null;
  scanning: number;
}) {
  const tail = account?.userId ? account.userId.slice(-7) : "";
  const label =
    state === "offline"
      ? "Chưa kết nối tiện ích"
      : state === "busy"
        ? `Đang quét ${scanning} kênh`
        : `Tiện ích sẵn sàng, TK phụ …${tail}`;
  const content = (
    <Flex vertical gap={8} style={{ maxWidth: 340 }}>
      <Typography.Text>
        Quét bằng tài khoản phụ {account?.userId ?? ""} trong cửa sổ ẩn danh, nên Facebook chính của bạn không bị ảnh
        hưởng. Giữ trang này mở: lượt quét (kể cả do Claude tạo qua MCP) chạy trong Chrome này, cuộn chậm như người
        thật.
      </Typography.Text>
      <Typography.Link onClick={openExtensionOptions}>Đổi tài khoản phụ</Typography.Link>
    </Flex>
  );
  const chip = (
    <Button size="small" aria-label={label}>
      <Badge
        status={state === "ready" ? "success" : state === "busy" ? "warning" : "error"}
        text={label}
        styles={{ indicator: { marginInlineEnd: 4 } }}
      />
    </Button>
  );
  return state === "offline" ? chip : <Popover content={content}>{chip}</Popover>;
}

/** What is missing, in full, while the extension cannot scan. */
export function ScannerHelp({
  version,
  current,
  account,
}: {
  version: string;
  current: boolean;
  account: ScanAccount | null;
}) {
  if (!current) {
    return (
      <Alert
        type="info"
        showIcon
        title={version ? `Tiện ích bản ${version} chưa quét được đối thủ` : "Chưa thấy tiện ích Reels Studio"}
        description="Cài hoặc cập nhật tiện ích (thư mục extension/ của dự án, bản 1.5.0 trở lên) trong Chrome, rồi tải lại trang."
      />
    );
  }
  const missing = [];
  if (!account?.userId) missing.push("lưu cookie của tài khoản Facebook phụ");
  if (account && !account.incognito)
    missing.push('bật "Cho phép ở chế độ ẩn danh" cho tiện ích trong chrome://extensions');
  return (
    <Alert
      type="warning"
      showIcon
      title="Chưa quét được: cần tài khoản Facebook phụ"
      description={
        <Flex vertical gap={8} align="start">
          <span>
            Lượt quét chỉ chạy bằng tài khoản phụ, trong cửa sổ ẩn danh, để Facebook chính của bạn không bị ảnh hưởng.
            Cookie chỉ lưu trong tiện ích của Chrome này, không gửi lên máy chủ. Còn thiếu: {missing.join("; ") || "…"}.
          </span>
          <Button onClick={openExtensionOptions}>Cài đặt tài khoản phụ</Button>
        </Flex>
      }
    />
  );
}
