"use client";

import { DeleteOutlined, EditOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Input, Popconfirm, Select, Spin, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { SettingsHeader } from "@/components/settings/SettingsBlocks";
import { api, errorMessage, type EditTemplate, type EditTemplates } from "@/lib/api";

/**
 * "Mẫu dựng": the app's own template and the team's (saved from a video in the studio's "Tự dựng"), the one put on
 * every new video once its scenes are written, and renaming or removing the team's.
 */
export default function EditTemplatesPage() {
  const { message } = App.useApp();
  const [list, setList] = useState<EditTemplates | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(
    async (call: () => Promise<EditTemplates>, done?: string) => {
      setBusy(true);
      try {
        setList(await call());
        if (done) message.success(done);
      } catch (err) {
        message.error(errorMessage(err));
      } finally {
        setBusy(false);
      }
    },
    [message],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void run(() => api<EditTemplates>("/edit-templates"));
  }, [run]);

  return (
    <>
      <SettingsHeader
        title="Mẫu dựng"
        description="Mẫu dựng gồm chuyển cảnh, màu, âm thanh và lớp chữ cuối video, áp được cho cả video bằng “Tự dựng” trong xem trước. Lưu mẫu mới từ một video ưng ý ở đó."
      />
      {list === null ? (
        <Spin />
      ) : (
        <Flex vertical gap={16}>
          <Card size="small" title="Video mới tự áp mẫu">
            <Flex vertical gap={8}>
              <Select
                aria-label="Mẫu cho video mới"
                style={{ maxWidth: 360 }}
                value={list.default === null ? "none" : String(list.default)}
                disabled={busy}
                options={[
                  { value: "none", label: "Không áp mẫu nào" },
                  ...list.templates.map((item) => ({ value: String(item.id), label: item.name })),
                ]}
                onChange={(value) =>
                  void run(
                    () =>
                      api<EditTemplates>("/edit-templates/default", "PUT", {
                        template: value === "none" ? null : value === "app" ? "app" : Number(value),
                      }),
                    "Đã lưu mẫu cho video mới",
                  )
                }
              />
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Áp ngay khi kịch bản được viết xong (AI viết, nhân bản hoặc tự viết). Video đã có giữ nguyên.
              </Typography.Text>
            </Flex>
          </Card>
          {list.templates.map((item) => (
            <TemplateCard key={item.id} template={item} isDefault={list.default === item.id} busy={busy} run={run} />
          ))}
        </Flex>
      )}
    </>
  );
}

function TemplateCard({
  template,
  isDefault,
  busy,
  run,
}: {
  template: EditTemplate;
  isDefault: boolean;
  busy: boolean;
  run: (call: () => Promise<EditTemplates>, done?: string) => Promise<void>;
}) {
  const [renaming, setRenaming] = useState<string | null>(null);
  return (
    <Card
      size="small"
      data-testid="template-card"
      title={
        renaming === null ? (
          <Flex align="center" gap={8}>
            <span>{template.name}</span>
            {template.builtin && <Tag>Có sẵn</Tag>}
            {isDefault && <Tag color="orange">Video mới tự áp</Tag>}
          </Flex>
        ) : (
          <Input
            aria-label="Tên mẫu"
            autoFocus
            value={renaming}
            maxLength={80}
            onChange={(event) => setRenaming(event.target.value)}
            onPressEnter={() =>
              void run(
                () => api<EditTemplates>(`/edit-templates/${template.id}`, "PATCH", { name: renaming }),
                "Đã đổi tên mẫu",
              ).then(() => setRenaming(null))
            }
            onBlur={() => setRenaming(null)}
          />
        )
      }
      extra={
        !template.builtin && (
          <Flex gap={4}>
            <Button
              size="small"
              type="text"
              aria-label={`Đổi tên ${template.name}`}
              icon={<EditOutlined />}
              disabled={busy}
              onClick={() => setRenaming(template.name)}
            />
            <Popconfirm
              title={`Xoá mẫu “${template.name}”?`}
              description={isDefault ? "Video mới sẽ không còn tự áp mẫu nào." : undefined}
              okText="Xoá"
              cancelText="Huỷ"
              okButtonProps={{ danger: true }}
              onConfirm={() =>
                void run(() => api<EditTemplates>(`/edit-templates/${template.id}`, "DELETE"), "Đã xoá mẫu")
              }
            >
              <Button
                size="small"
                type="text"
                danger
                aria-label={`Xoá ${template.name}`}
                icon={<DeleteOutlined />}
                disabled={busy}
              />
            </Popconfirm>
          </Flex>
        )
      }
    >
      <Flex vertical gap={2}>
        {template.summary.map((line) => (
          <Typography.Text key={line} type="secondary">
            {line}
          </Typography.Text>
        ))}
      </Flex>
    </Card>
  );
}
