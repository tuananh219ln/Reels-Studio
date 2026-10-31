"use client";

import { App, Card, Flex, Switch, Table, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";

type Source = {
  id: string;
  label: string;
  kinds: string;
  key_name: string | null;
  configured: boolean;
  enabled: boolean;
};
type Sources = { sources: Source[]; ai_images: { configured: boolean; model: string } };

/** Which stock libraries the picker and "Tìm ảnh khác" offer. Keys live in the server's .env. */
export default function SourcesPage() {
  const { message } = App.useApp();
  const [data, setData] = useState<Sources | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api<Sources>("/settings/sources"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void load();
  }, [load]);

  async function toggle(source: Source, enabled: boolean) {
    setBusy(source.id);
    try {
      setData(await api<Sources>(`/settings/sources/${source.id}`, "PUT", { enabled }));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <Typography.Title level={2} style={{ margin: 0, fontWeight: 600 }}>
        Nguồn tư liệu
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ margin: "8px 0 16px", maxWidth: 760 }}>
        Các kho ảnh và video miễn phí mà hộp “Chọn từ kho ảnh/video” và nút “Tìm ảnh khác” dùng. Tắt một nguồn thì nó
        biến khỏi hộp chọn của cả nhóm. Key của từng nguồn nằm trong file .env của máy chủ.
      </Typography.Paragraph>
      <Table<Source>
        rowKey="id"
        loading={data === null}
        dataSource={data?.sources ?? []}
        pagination={false}
        scroll={{ x: "max-content" }}
        style={{ maxWidth: 900 }}
        columns={[
          { title: "Nguồn", dataIndex: "label" },
          { title: "Cung cấp", dataIndex: "kinds" },
          {
            title: "Cấu hình",
            render: (_, row) =>
              row.configured ? <Tag color="success">Sẵn sàng</Tag> : <Tag color="warning">Thiếu {row.key_name}</Tag>,
          },
          {
            title: "Hiện trong hộp chọn",
            render: (_, row) => (
              <Switch
                aria-label={`Bật ${row.label}`}
                checked={row.enabled}
                loading={busy === row.id}
                onChange={(enabled) => toggle(row, enabled)}
              />
            ),
          },
        ]}
      />
      {data && (
        <Card size="small" style={{ maxWidth: 900, marginTop: 16 }}>
          <Flex wrap gap={8} align="center">
            <Typography.Text strong>Ảnh AI cho cảnh thiếu (Gemini):</Typography.Text>
            {data.ai_images.configured ? (
              <Tag color="success">Sẵn sàng · {data.ai_images.model}</Tag>
            ) : (
              <Tag color="warning">Thiếu IMAGE_GEN_API_KEY</Tag>
            )}
          </Flex>
        </Card>
      )}
    </>
  );
}
