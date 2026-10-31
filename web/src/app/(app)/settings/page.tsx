"use client";

import { App, Button, Card, Flex, Input, Spin, Typography } from "antd";
import { useEffect, useState } from "react";
import { api, errorMessage, type FacebookSettings } from "@/lib/api";

export default function SettingsPage() {
  const { message } = App.useApp();
  const [saved, setSaved] = useState<FacebookSettings | null>(null);
  const [pageId, setPageId] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    api<FacebookSettings>("/settings/facebook")
      .then((data) => {
        setSaved(data);
        setPageId(data.page_id);
      })
      .catch((err) => message.error(errorMessage(err)));
  }, [message]);

  async function save() {
    setBusy(true);
    setResult(null);
    try {
      setSaved(await api<FacebookSettings>("/settings/facebook", "PUT", { page_id: pageId, token }));
      setToken("");
      message.success("Đã lưu");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    setTesting(true);
    setResult(null);
    try {
      const { page_name } = await api<{ page_name: string }>("/settings/facebook/test", "POST");
      setResult({ ok: true, text: `Kết nối được với Page “${page_name}”` });
    } catch (err) {
      setResult({ ok: false, text: errorMessage(err) });
    } finally {
      setTesting(false);
    }
  }

  if (!saved) {
    return (
      <Flex justify="center" style={{ padding: 48 }}>
        <Spin size="large" />
      </Flex>
    );
  }

  return (
    <>
      <Typography.Title level={2} style={{ marginTop: 0, fontWeight: 600 }}>Cài đặt</Typography.Title>
      <Card title="Facebook Page" size="small" style={{ maxWidth: 640 }}>
        <Flex vertical gap={12}>
          <Typography.Text type="secondary">
            Tạo trong Meta Business Suite: Cài đặt doanh nghiệp, Người dùng hệ thống, Tạo token cho Page với quyền
            pages_show_list, pages_read_engagement, pages_manage_posts, chọn không hết hạn.
          </Typography.Text>
          <div>
            <Typography.Text strong style={{ display: "block", marginBottom: 4 }}>Page ID</Typography.Text>
            <Input aria-label="Page ID" value={pageId} inputMode="numeric"
              onChange={(event) => setPageId(event.target.value)} />
          </div>
          <div>
            <Typography.Text strong style={{ display: "block", marginBottom: 4 }}>Token của Page</Typography.Text>
            <Input.Password aria-label="Token của Page" value={token} autoComplete="new-password"
              placeholder={saved.has_token ? "Đã lưu, để trống nếu không đổi" : undefined}
              onChange={(event) => setToken(event.target.value)} />
            <Typography.Text type="secondary">Token được mã hoá khi lưu và không hiện lại trên màn hình.</Typography.Text>
          </div>
          <Flex wrap gap={8} align="center">
            <Button type="primary" loading={busy} disabled={!pageId.trim()} onClick={save}>Lưu</Button>
            <Button loading={testing} disabled={!saved.has_token} onClick={test}>Kiểm tra kết nối</Button>
          </Flex>
          {result && (
            <Typography.Text type={result.ok ? "success" : "danger"} data-testid="facebook-test">
              {result.text}
            </Typography.Text>
          )}
        </Flex>
      </Card>
    </>
  );
}
