"use client";

import { Alert, Button, Flex, Modal, Typography } from "antd";
import { useEffect, useState, useSyncExternalStore } from "react";

// Chrome and Edge offer a one-tap install through this event; Safari on iPhone never fires it.
type InstallPrompt = Event & { prompt: () => Promise<void> };

/** Standalone means the app was opened from the home screen, so it is already installed. */
function isInstalled() {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function isIos() {
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

/** Whether the account menu should offer "Cài app": not when the app is already running installed. */
export function useCanInstall() {
  return useBrowserFlag(() => !isInstalled());
}

/** A fact about this browser that never changes while the page is open; false while rendering on the server. */
function useBrowserFlag(read: () => boolean) {
  return useSyncExternalStore(
    () => () => undefined,
    read,
    () => false,
  );
}

export default function InstallAppModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);
  const ios = useBrowserFlag(isIos);

  useEffect(() => {
    const onPrompt = (event: Event) => {
      event.preventDefault();
      setPrompt(event as InstallPrompt);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);

  async function install() {
    await prompt?.prompt();
    setPrompt(null);
    onClose();
  }

  return (
    <Modal open={open} onCancel={onClose} footer={null} title="Cài app lên điện thoại" width={520}>
      <Flex vertical gap={16}>
        <Typography.Paragraph style={{ marginBottom: 0 }}>
          Reels Studio cài được như một app: có biểu tượng trên màn hình chính, mở toàn màn hình, không có thanh địa
          chỉ. Vẫn dùng bình thường trên máy tính qua trình duyệt, cùng một tài khoản và cùng dữ liệu.
        </Typography.Paragraph>
        {prompt && (
          <Button type="primary" size="large" onClick={install}>
            Cài ngay
          </Button>
        )}
        <div>
          <Typography.Text strong>iPhone / iPad (Safari)</Typography.Text>
          <ol style={{ margin: "4px 0 0", paddingInlineStart: 20 }}>
            <li>Mở trang này bằng Safari (không phải Chrome hay Zalo).</li>
            <li>Bấm nút Chia sẻ (hình vuông có mũi tên lên) ở thanh dưới.</li>
            <li>Chọn “Thêm vào Màn hình chính”, rồi bấm “Thêm”.</li>
          </ol>
        </div>
        <div>
          <Typography.Text strong>Android (Chrome)</Typography.Text>
          <ol style={{ margin: "4px 0 0", paddingInlineStart: 20 }}>
            <li>Bấm nút ⋮ ở góc trên bên phải.</li>
            <li>Chọn “Cài đặt ứng dụng” (hoặc “Thêm vào Màn hình chính”).</li>
            <li>Bấm “Cài đặt”.</li>
          </ol>
        </div>
        <div>
          <Typography.Text strong>Máy tính (Chrome, Edge)</Typography.Text>
          <p style={{ margin: "4px 0 0" }}>Bấm biểu tượng cài đặt ở cuối thanh địa chỉ, rồi chọn “Cài đặt”.</p>
        </div>
        {ios && <Alert type="info" showIcon title="Trên iPhone chỉ Safari mới có mục “Thêm vào Màn hình chính”." />}
        <Alert
          type="warning"
          showIcon
          title="App cần mạng để chạy"
          description="Dữ liệu và video nằm trên máy chủ, nên mất mạng thì app không mở được nội dung. Khi có bản mới, mở lại app là tự cập nhật."
        />
      </Flex>
    </Modal>
  );
}
