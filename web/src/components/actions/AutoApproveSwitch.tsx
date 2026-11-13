"use client";

import { api, errorMessage } from "@/lib/api";
import { App, Flex, Switch, Tooltip, Typography } from "antd";
import { useEffect, useState } from "react";

/** "Tự duyệt": the member's own switch. On, a video they made is approved the moment its render is done, when nothing
 * needs a look (no warning, a time and a Page); the rest wait for "Duyệt", and Muse tells them on WhatsApp. */
export default function AutoApproveSwitch() {
  const { message } = App.useApp();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    api<{ enabled: boolean }>("/me/auto-approve").then(
      (data) => live && setEnabled(data.enabled),
      (err) => live && message.error(errorMessage(err)),
    );
    return () => {
      live = false;
    };
  }, [message]);
  async function change(next: boolean) {
    setBusy(true);
    try {
      setEnabled((await api<{ enabled: boolean }>("/me/auto-approve", "PUT", { enabled: next })).enabled);
      message.success(next ? "Đã bật tự duyệt" : "Đã tắt tự duyệt");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Tooltip title="Bật: video của bạn render xong là tự hẹn đăng theo giờ trong kế hoạch, nếu không có cảnh báo và đã có Page của bạn. Video còn lại chờ bạn duyệt, Muse sẽ báo qua WhatsApp.">
      <Flex align="center" gap={8}>
        <Switch
          aria-label="Tự duyệt khi render xong"
          checked={enabled === true}
          loading={enabled === null || busy}
          onChange={(next) => void change(next)}
        />
        <Typography.Text>Tự duyệt khi render xong</Typography.Text>
      </Flex>
    </Tooltip>
  );
}
