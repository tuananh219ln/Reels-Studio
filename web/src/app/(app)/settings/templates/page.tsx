"use client";

import { useMe } from "@/components/MeContext";
import { DeleteOutlined, EditOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Input, Popconfirm, Select, Spin, Tag, theme, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { SettingsHeader } from "@/components/settings/SettingsBlocks";
import { LastEdit, PageHistory, useLatestEdits } from "@/components/settings/SharedHistory";
import { api, errorMessage, type EditTemplate, type EditTemplates } from "@/lib/api";

/**
 * "Mẫu dựng": the app's own template and the members' (saved from a video in the studio's "Tự dựng"), the signed-in
 * member's own one put on their new videos once its scenes are written, and renaming or removing templates.
 */
export default function EditTemplatesPage() {
  const { message } = App.useApp();
  const [list, setList] = useState<EditTemplates | null>(null);
  const [busy, setBusy] = useState(false);
  const { token } = theme.useToken();
  // The saved templates' latest change, read again after every change (each answers with the list anew).
  const latest = Object.values(useLatestEdits("edit_template", list)).sort((a, b) => b.id - a.id)[0];

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
        actions={<PageHistory entityType="edit_template" title="Mẫu dựng" />}
      />
      {list === null ? (
        <Spin />
      ) : (
        <Flex vertical gap={16}>
          {/* The one card of this shared page that is the member's own. */}
          <Card
            size="small"
            title="Video mới của tôi tự áp mẫu"
            extra={<Tag color="blue">Của tôi</Tag>}
            style={{ borderColor: token.colorPrimaryBorder }}
          >
            <Flex vertical gap={8}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Chỉ áp cho video mới do bạn tạo.
              </Typography.Text>
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
                Áp ngay khi kịch bản được viết xong (AI viết, nhân bản hoặc tự viết). Video đã có giữ nguyên. Cảnh kết
                kêu gọi của kịch bản được giữ: lớp chữ cuối của mẫu không chèn vào cảnh đó.
              </Typography.Text>
            </Flex>
          </Card>
          {list.templates.map((item) => (
            <TemplateCard key={item.id} template={item} isDefault={list.default === item.id} busy={busy} run={run} />
          ))}
          <LastEdit entry={latest} entityType="edit_template" title="Mẫu dựng" />
        </Flex>
      )}
    </>
  );
}

/** Said before a template is deleted: who and which groups put it on their new videos, and stop doing so. */
function usage(template: EditTemplate): string {
  const parts = [];
  if (template.members_using > 0) parts.push(`${template.members_using} người đang chọn làm mẫu cho video mới`);
  if (template.topics.length > 0) {
    parts.push(`${template.topics.length} nhóm đang giữ (${template.topics.map((topic) => topic.name).join(", ")})`);
  }
  return parts.length === 0
    ? "Chưa ai dùng mẫu này cho video mới."
    : `${parts.join(" và ")}. Xoá thì video mới của họ không còn tự áp mẫu này; video đã có giữ nguyên.`;
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
  const { me } = useMe();
  return (
    <Card
      size="small"
      data-testid="template-card"
      title={
        renaming === null ? (
          <Flex align="center" gap={8}>
            <span>{template.name}</span>
            {template.builtin && <Tag>Có sẵn</Tag>}
            {isDefault && <Tag color="orange">Video mới của tôi tự áp</Tag>}
            {template.topics.map((topic) => (
              <Tag key={topic.id} color="geekblue">
                Nhóm {topic.name}
              </Tag>
            ))}
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
        // Only whoever saved it renames or deletes it.
        !template.builtin &&
        template.created_by_id === me.id && (
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
              description={<span data-testid="template-delete-usage">{usage(template)}</span>}
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
