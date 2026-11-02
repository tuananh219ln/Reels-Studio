"use client";

import { Alert, App, Button, Card, Empty, Flex, Spin, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import PageHeader from "@/components/PageHeader";
import { api, errorMessage, formatDateTime } from "@/lib/api";

type Connection = { id: number; scopes: string; expires_at: string };
type Consent = { ticket: string; email: string; scopes: string[] };

export default function ChatGptPage() {
  const { message } = App.useApp();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [consent, setConsent] = useState<Consent | null>(null);
  const [serverUrl, setServerUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [revoking, setRevoking] = useState<number | null>(null);

  const load = useCallback(() => {
    const ticket = new URLSearchParams(window.location.hash.slice(1)).get("ticket");
    return Promise.all([
      api<{ server_url: string }>("/mcp/config"),
      api<Connection[]>("/mcp/connections"),
      ticket ? api<Omit<Consent, "ticket">>(`/mcp/authorizations/${encodeURIComponent(ticket)}`) : null,
    ])
      .then(([config, rows, details]) => {
        setServerUrl(config.server_url);
        setConnections(rows);
        setConsent(details && ticket ? { ...details, ticket } : null);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    void load();
    window.addEventListener("hashchange", load);
    return () => window.removeEventListener("hashchange", load);
  }, [load]);

  async function revoke(id: number) {
    setRevoking(id);
    try {
      await api(`/mcp/connections/${id}`, "DELETE");
      setConnections((rows) => rows.filter((row) => row.id !== id));
      message.success("Đã thu hồi kết nối ChatGPT");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setRevoking(null);
    }
  }

  return (
    <>
      <PageHeader title="Kết nối ChatGPT" description="Cấp quyền và quản lý các kết nối ChatGPT của bạn." />
      <Flex vertical gap={16} style={{ maxWidth: 820 }}>
        {loading && <Spin />}
        {error && <Alert type="warning" showIcon title={error} action={<Button onClick={load}>Thử lại</Button>} />}
        {!loading && !error && consent && (
          <Card
            title={
              <Typography.Title level={4} style={{ margin: 0 }}>
                Cho phép ChatGPT kết nối?
              </Typography.Title>
            }
          >
            <Typography.Paragraph>
              Bạn đang dùng tài khoản <strong>{consent.email}</strong>.
            </Typography.Paragraph>
            <Typography.Paragraph>
              ChatGPT được đọc video, kịch bản, nhóm chủ đề và trạng thái công việc của cả nhóm.
            </Typography.Paragraph>
            {consent.scopes.includes("reels:write") && (
              <Alert
                type="warning"
                showIcon
                title="Quyền sửa và tạo công việc"
                description="ChatGPT còn được sửa chữ, lời đọc, caption; tạo video và yêu cầu render. Tạo kịch bản và giọng đọc có thể dùng phí dịch vụ AI của nhóm."
                style={{ marginBottom: 16 }}
              />
            )}
            <Typography.Paragraph>
              Kết nối không được đăng bài, xóa video hoặc thay đổi tài khoản và API key. Quyền hết hạn sau tối đa 30
              ngày và mất hiệu lực khi phiên đăng nhập này bị thu hồi.
            </Typography.Paragraph>
            {/* A native form follows the OAuth redirect without exposing credentials to client-side code. */}
            <form method="post" action="/api/mcp/oauth/consent">
              <input type="hidden" name="ticket" value={consent.ticket} />
              <Flex wrap gap={8}>
                <Button type="primary" htmlType="submit" name="decision" value="allow">
                  Cho phép kết nối
                </Button>
                <Button htmlType="submit" name="decision" value="deny">
                  Từ chối
                </Button>
              </Flex>
            </form>
          </Card>
        )}
        {serverUrl && (
          <Card title="Thêm Reels Studio vào ChatGPT">
            <Typography.Paragraph>
              Trong ChatGPT, mở mục ứng dụng/plugin, chọn thêm máy chủ MCP riêng và dán địa chỉ dưới đây. Chọn xác thực
              OAuth, rồi đăng nhập và cấp quyền bằng tài khoản Reels Studio của bạn.
            </Typography.Paragraph>
            <Typography.Paragraph copyable={{ text: serverUrl }} code style={{ overflowWrap: "anywhere" }}>
              {serverUrl}
            </Typography.Paragraph>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              Quyền thêm kết nối phụ thuộc cài đặt workspace ChatGPT. Khi yêu cầu tạo kịch bản hoặc render, dịch vụ AI
              được cấu hình trong Reels Studio vẫn có thể tính phí.
            </Typography.Paragraph>
          </Card>
        )}
        {!loading && !error && (
          <Card title="Các kết nối của bạn">
            {!connections.length ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Bạn chưa có kết nối ChatGPT nào." />
            ) : (
              <Flex vertical gap={16}>
                {connections.map((row) => (
                  <Flex key={row.id} wrap gap={12} align="center" justify="space-between">
                    <div>
                      <Typography.Text strong>Kết nối #{row.id}</Typography.Text>{" "}
                      <Tag>{row.scopes.includes("reels:write") ? "Đọc và sửa" : "Chỉ đọc"}</Tag>
                      <Typography.Text type="secondary" style={{ display: "block" }}>
                        Hết hạn {formatDateTime(row.expires_at)}
                      </Typography.Text>
                    </div>
                    <Button danger loading={revoking === row.id} onClick={() => revoke(row.id)}>
                      Thu hồi kết nối
                    </Button>
                  </Flex>
                ))}
              </Flex>
            )}
          </Card>
        )}
      </Flex>
    </>
  );
}
