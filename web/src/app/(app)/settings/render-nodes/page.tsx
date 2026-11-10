"use client";

import EmptyState from "@/components/EmptyState";
import { useMe } from "@/components/MeContext";
import { DeleteOutlined, DesktopOutlined, PlusOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Flex, Input, Popconfirm, Spin, Switch, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { SettingsHeader } from "@/components/settings/SettingsBlocks";
import { LastEdit, PageHistory, useLatestEdits } from "@/components/settings/SharedHistory";
import StatusText from "@/components/StatusText";
import { api, errorMessage, formatDateTime } from "@/lib/api";

type RenderNode = {
  id: number;
  name: string;
  created_by: string;
  /** Only they remove it. */
  created_by_id: number;
  created_at: string;
  last_seen_at: string | null;
  online: boolean;
};
type Overview = { enabled: boolean; waiting: number; nodes: RenderNode[] };

/** Cài đặt › Máy render: a member's computer renders the team's videos and motion scenes (api render_nodes.py). */
export default function RenderNodesPage() {
  const { message } = App.useApp();
  const { me } = useMe();
  const [data, setData] = useState<Overview | null>(null);
  const [name, setName] = useState("");
  const [adding, setAdding] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  // Read again after every change: each one answers with the machines anew.
  const latest = useLatestEdits("render_settings", data);

  const load = useCallback(async () => {
    try {
      setData(await api<Overview>("/render-nodes"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the first load and a refresh every 15 s, so a machine's status stays current; state is set only after the request answers
    void load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [load]);

  async function add() {
    setAdding(true);
    try {
      const made = await api<{ token: string }>("/render-nodes", "POST", { name: name.trim() });
      setToken(made.token);
      setName("");
      await load();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setAdding(false);
    }
  }

  async function toggle(enabled: boolean) {
    try {
      setData(await api<Overview>("/render-nodes/setting", "PUT", { enabled }));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  async function remove(node: RenderNode) {
    try {
      setData(await api<Overview>(`/render-nodes/${node.id}`, "DELETE"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  if (!data) return <Spin />;
  const server = typeof window === "undefined" ? "" : window.location.origin;
  const command = `$env:REELS_SERVER="${server}"; $env:REELS_NODE_TOKEN="${token ?? "<token>"}"; python -m reels_api node`;
  const anyOnline = data.nodes.some((node) => node.online);

  return (
    <Flex vertical gap={16} style={{ maxWidth: 820 }}>
      <SettingsHeader
        title="Máy render"
        description="Máy render của thành viên dựng video cho cả nhóm: máy nào đang rảnh nhận job đang chờ lâu nhất, của bất kỳ ai."
        actions={<PageHistory entityType="render_settings" title="Máy render" />}
      />
      <Card size="small">
        <Flex vertical gap={8}>
          <Flex gap={12} align="center" wrap>
            <Switch checked={data.enabled} onChange={toggle} aria-label="Render trên máy render" />
            <Typography.Text strong>Render và cảnh động chạy trên máy render</Typography.Text>
          </Flex>
          <Typography.Text type="secondary">
            Bật: máy chủ chỉ chuẩn bị (giọng đọc, kiểm tra, gom file), rồi máy render của thành viên dựng MP4 và cảnh
            động. Khi không có máy nào đang chạy, job đợi đến khi máy bật lại. Tắt: máy chủ tự render như trước.
          </Typography.Text>
          {data.enabled && !anyOnline && (
            <Alert
              type="warning"
              showIcon
              title={`Chưa có máy render nào đang chạy${data.waiting ? `: ${data.waiting} job đang đợi` : ""}`}
              description="Bật chương trình máy render trên máy của bạn, hoặc tắt công tắc này để máy chủ tự render."
            />
          )}
        </Flex>
        <LastEdit entry={latest["1"]} entityType="render_settings" entityId={1} title="Máy render" />
      </Card>

      <Card title="Các máy render" size="small">
        {data.nodes.length ? (
          <Flex vertical gap={12}>
            {data.nodes.map((node) => (
              <Flex key={node.id} gap={12} align="center" justify="space-between" wrap>
                <Flex gap={10} align="center">
                  <DesktopOutlined />
                  <div>
                    <Typography.Text strong>{node.name}</Typography.Text>{" "}
                    <StatusText tone={node.online ? "success" : "idle"}>
                      {node.online ? "Đang chạy" : "Đang tắt"}
                    </StatusText>
                    <Typography.Text type="secondary" style={{ display: "block", fontSize: 12 }}>
                      {node.last_seen_at ? `Lần cuối ${formatDateTime(node.last_seen_at)}` : "Chưa kết nối lần nào"},
                      thêm bởi {node.created_by}
                    </Typography.Text>
                  </div>
                </Flex>
                {node.created_by_id === me.id && (
                  <Popconfirm
                    title="Xoá máy render?"
                    description="Token của máy hết dùng được; job máy đang dựng được trả lại hàng đợi."
                    okText="Xoá"
                    cancelText="Huỷ"
                    onConfirm={() => remove(node)}
                  >
                    <Button danger icon={<DeleteOutlined />}>
                      Xoá
                    </Button>
                  </Popconfirm>
                )}
              </Flex>
            ))}
          </Flex>
        ) : (
          <EmptyState description="Chưa có máy render nào" />
        )}
      </Card>

      <Card title="Thêm máy render" size="small">
        <Flex vertical gap={12}>
          <Flex gap={8} wrap>
            <Input
              aria-label="Tên máy"
              placeholder="Tên máy, ví dụ: PC nhà An…"
              value={name}
              maxLength={60}
              onChange={(event) => setName(event.target.value)}
              style={{ flex: "1 1 240px" }}
            />
            <Button type="primary" icon={<PlusOutlined />} loading={adding} disabled={!name.trim()} onClick={add}>
              Thêm máy
            </Button>
          </Flex>
          {token && (
            <Alert
              type="success"
              showIcon
              title="Token của máy chỉ hiện một lần: chép lệnh dưới đây ngay"
              description={
                <Typography.Paragraph copyable={{ text: command }} code style={{ overflowWrap: "anywhere", margin: 0 }}>
                  {command}
                </Typography.Paragraph>
              }
            />
          )}
          <Typography.Text type="secondary">
            Trên máy render cần Python 3.12 đã cài Reels Studio (thư mục api và worker), FFmpeg, và cho cảnh động thêm
            Node 22 với HyperFrames. Chạy lệnh trong PowerShell ở thư mục api; hướng dẫn đầy đủ ở docs/deployment.md.
          </Typography.Text>
        </Flex>
      </Card>
    </Flex>
  );
}
