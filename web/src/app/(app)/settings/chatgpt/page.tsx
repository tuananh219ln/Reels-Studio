"use client";

import { Alert, App, Button, Card, Empty, Flex, Spin, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { SettingsHeader } from "@/components/settings/SettingsBlocks";
import { api, errorMessage, formatDateTime } from "@/lib/api";

type Connection = { id: number; app: string; scopes: string; expires_at: string };
type Consent = {
  ticket: string;
  email: string;
  scopes: string[];
  app: string;
  redirect_host: string;
  loopback: boolean;
};

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

  async function revoke(row: Connection) {
    setRevoking(row.id);
    try {
      await api(`/mcp/connections/${row.id}`, "DELETE");
      setConnections((rows) => rows.filter((other) => other.id !== row.id));
      message.success(`Đã thu hồi kết nối ${row.app}`);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setRevoking(null);
    }
  }

  return (
    <>
      <SettingsHeader
        title="Kết nối ChatGPT / Claude"
        description="Cấp quyền và quản lý các kết nối ChatGPT, Claude, Claude Code và Muse của bạn."
      />
      <Flex vertical gap={16} style={{ maxWidth: 820 }}>
        {loading && <Spin />}
        {error && <Alert type="warning" showIcon title={error} action={<Button onClick={load}>Thử lại</Button>} />}
        {!loading && !error && consent && (
          <Card
            title={
              <Typography.Title level={4} style={{ margin: 0 }}>
                Cho phép {consent.app} kết nối?
              </Typography.Title>
            }
          >
            <Typography.Paragraph>
              Bạn đang dùng tài khoản <strong>{consent.email}</strong>. Quyền sẽ được gửi về{" "}
              <Typography.Text code>{consent.redirect_host}</Typography.Text>.
            </Typography.Paragraph>
            {consent.loopback && (
              <Alert
                type="warning"
                showIcon
                title="Kết nối với một chương trình trên máy tính"
                description="Chỉ cho phép nếu bạn vừa tự kết nối Reels Studio trong Claude Code trên máy này. Một chương trình khác trên máy cũng có thể nhận địa chỉ này."
                style={{ marginBottom: 16 }}
              />
            )}
            <Typography.Paragraph>
              {consent.app} được đọc video, kịch bản, nhóm chủ đề, sản phẩm affiliate và trạng thái công việc của cả
              nhóm.
            </Typography.Paragraph>
            {consent.scopes.includes("reels:write") && (
              <Alert
                type="warning"
                showIcon
                title="Quyền sửa và tạo công việc"
                description={`${consent.app} còn được sửa chữ, lời đọc, caption; tạo video, gắn ảnh hoặc clip từ link, gắn sản phẩm và yêu cầu render. Tạo kịch bản bằng AI của nhóm và giọng đọc có thể dùng phí dịch vụ AI của nhóm.`}
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
          <Card title="Thêm Reels Studio vào ChatGPT, Claude hoặc Muse">
            <Typography.Paragraph copyable={{ text: serverUrl }} code style={{ overflowWrap: "anywhere" }}>
              {serverUrl}
            </Typography.Paragraph>
            <Typography.Paragraph>
              <strong>ChatGPT:</strong> mở mục ứng dụng/plugin, chọn thêm máy chủ MCP riêng, dán địa chỉ trên và chọn
              xác thực OAuth.
            </Typography.Paragraph>
            <Typography.Paragraph>
              <strong>Claude (web, Desktop):</strong> mở Cài đặt › Connectors, chọn thêm connector tùy chỉnh và dán địa
              chỉ trên.
            </Typography.Paragraph>
            <Typography.Paragraph>
              <strong>Claude Code:</strong> chạy lệnh dưới đây, rồi gõ <Typography.Text code>/mcp</Typography.Text> để
              đăng nhập.
            </Typography.Paragraph>
            <Typography.Paragraph
              copyable={{ text: `claude mcp add --transport http reels-studio ${serverUrl}` }}
              code
              style={{ overflowWrap: "anywhere" }}
            >
              {`claude mcp add --transport http reels-studio ${serverUrl}`}
            </Typography.Paragraph>
            <Typography.Paragraph>
              <strong>Muse:</strong> trong luồng kết nối công cụ MCP của Muse, dán địa chỉ trên rồi bấm Kết nối.
            </Typography.Paragraph>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              Sau đó đăng nhập và cấp quyền bằng tài khoản Reels Studio của bạn. Claude dùng gói Claude của chính bạn,
              nên tự viết kịch bản trong Claude không tốn phí AI của nhóm; tạo kịch bản bằng AI của nhóm, giọng đọc và
              render vẫn dùng dịch vụ được cấu hình trong Reels Studio.
            </Typography.Paragraph>
          </Card>
        )}
        {!loading && !error && (
          <Card title="Các kết nối của bạn">
            {!connections.length ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Bạn chưa có kết nối nào." />
            ) : (
              <Flex vertical gap={16}>
                {connections.map((row) => (
                  <Flex key={row.id} wrap gap={12} align="center" justify="space-between">
                    <div>
                      <Typography.Text strong>
                        {row.app} · Kết nối #{row.id}
                      </Typography.Text>{" "}
                      <Tag>{row.scopes.includes("reels:write") ? "Đọc và sửa" : "Chỉ đọc"}</Tag>
                      <Typography.Text type="secondary" style={{ display: "block" }}>
                        Hết hạn {formatDateTime(row.expires_at)}
                      </Typography.Text>
                    </div>
                    <Button danger loading={revoking === row.id} onClick={() => revoke(row)}>
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
