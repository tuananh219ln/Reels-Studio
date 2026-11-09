"use client";

import { SaveOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { App, Button, Flex, Input, Spin, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { api, errorMessage, type EditTemplates } from "@/lib/api";

/**
 * "Tự dựng" in the tools column: each "Mẫu dựng" (the app's own first, then the members') with what it does, put on
 * the whole video with one click (undone with Ctrl+Z); and "Lưu video này thành mẫu", the video's look as a new
 * team template. Templates are managed on Cấu hình › Mẫu dựng.
 */
export default function AutoEditPanel({
  editable,
  videoId,
  onApply,
}: {
  editable: boolean;
  videoId: number;
  onApply: (template: "app" | number, name: string) => void;
}) {
  const { message } = App.useApp();
  const [list, setList] = useState<EditTemplates | null>(null);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let open = true;
    api<EditTemplates>("/edit-templates").then(
      (loaded) => open && setList(loaded),
      (err) => message.error(errorMessage(err)),
    );
    return () => {
      open = false;
    };
  }, [message]);

  async function saveAsTemplate() {
    setSaving(true);
    try {
      setList(await api<EditTemplates>("/edit-templates", "POST", { name, video_id: videoId }));
      message.success(`Đã lưu mẫu “${name.trim()}”`);
      setName("");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Flex vertical gap={12} data-testid="auto-edit">
      <Typography.Text strong>Tự dựng</Typography.Text>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Áp một mẫu cho cả video: chuyển cảnh và màu được thay, âm và lớp chữ được thêm (không thêm trùng). Bấm Ctrl+Z để
        hoàn tác.
      </Typography.Text>
      {list === null ? (
        <Spin size="small" />
      ) : (
        <Flex vertical gap={8} role="list" aria-label="Mẫu dựng">
          {list.templates.map((template) => (
            <Flex
              key={template.id}
              vertical
              gap={4}
              role="listitem"
              data-testid="template"
              style={{ border: "1px solid #e7e8ea", borderRadius: 6, padding: "8px 10px" }}
            >
              <Flex align="center" gap={6} wrap>
                <Typography.Text strong style={{ flex: 1, minWidth: 0 }}>
                  {template.name}
                </Typography.Text>
                {list.default === template.id && <Tag color="orange">Video mới của tôi tự áp</Tag>}
              </Flex>
              {template.summary.map((line) => (
                <Typography.Text key={line} type="secondary" style={{ fontSize: 12 }}>
                  {line}
                </Typography.Text>
              ))}
              <Button
                size="small"
                icon={<ThunderboltOutlined />}
                disabled={!editable}
                aria-label={`Áp mẫu ${template.name}`}
                onClick={() => onApply(template.id, template.name)}
                style={{ alignSelf: "flex-start" }}
              >
                Áp cho cả video
              </Button>
            </Flex>
          ))}
        </Flex>
      )}
      <Flex vertical gap={6}>
        <Typography.Text strong style={{ fontSize: 13 }}>
          Lưu video này thành mẫu
        </Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Mẫu giữ chuyển cảnh các cảnh, màu dùng nhiều nhất, âm của cảnh đầu tiên có âm, âm và mức nhạc cảnh tiêu đề, và
          các lớp ở cảnh cuối.
        </Typography.Text>
        <Flex gap={6}>
          <Input
            aria-label="Tên mẫu mới"
            placeholder="Tên mẫu, ví dụ Vườn nhà ấm"
            value={name}
            maxLength={80}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => event.stopPropagation()}
          />
          <Button
            icon={<SaveOutlined />}
            loading={saving}
            disabled={!name.trim()}
            onClick={() => void saveAsTemplate()}
          >
            Lưu
          </Button>
        </Flex>
      </Flex>
    </Flex>
  );
}
