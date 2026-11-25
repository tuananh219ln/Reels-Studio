"use client";

import { App, Button, Card, Flex, Input, Radio, Switch, Typography } from "antd";
import { useState } from "react";
import { errorMessage, type KnowledgeTopic } from "@/lib/api";
import EditHistory from "@/components/EditHistory";

type Update = (body: Partial<KnowledgeTopic>) => Promise<KnowledgeTopic>;

/**
 * "Câu lưu ý y khoa": a health group's fixed reminder is written by the worker at the end of the last pinned comment,
 * not in the caption (api disclaimer.py). The sentence is changed here, in one place.
 */
export default function GroupDisclaimerCard({ topic, update }: { topic: KnowledgeTopic; update: Update }) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState(topic.medical_disclaimer_text);
  const [seen, setSeen] = useState(topic.medical_disclaimer_text);

  // The sentence the server holds replaces the box when the group changes under it.
  if (seen !== topic.medical_disclaimer_text) {
    setSeen(topic.medical_disclaimer_text);
    setText(topic.medical_disclaimer_text);
  }

  async function save(body: Partial<KnowledgeTopic>, done: string) {
    setBusy(true);
    try {
      await update(body);
      message.success(done);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Câu lưu ý y khoa"
      size="small"
      extra={
        <EditHistory
          entityType="knowledge_topic"
          entityId={topic.id}
          field="medical_disclaimer_text"
          title="Câu lưu ý y khoa"
          kind="text"
          current={topic.medical_disclaimer_text}
        />
      }
    >
      <Flex vertical gap={12}>
        <Flex gap={12} align="flex-start">
          <Switch
            aria-label="Câu lưu ý y khoa"
            checked={topic.medical_disclaimer_enabled}
            loading={busy}
            disabled={busy}
            onChange={(checked) =>
              void save(
                { medical_disclaimer_enabled: checked },
                checked ? "Đã bật câu lưu ý y khoa" : "Đã tắt câu lưu ý y khoa",
              )
            }
            style={{ marginTop: 2 }}
          />
          <Typography.Text type="secondary">
            Bài viết của nhóm không có câu lưu ý trong caption; app tự nối câu này vào cuối bình luận ghim cuối cùng khi
            đăng (không tạo thêm bình luận). Bài đã đăng không đổi.
          </Typography.Text>
        </Flex>
        <Radio.Group
          aria-label="Chỗ đặt câu lưu ý y khoa"
          value={topic.medical_disclaimer_position}
          disabled={busy || !topic.medical_disclaimer_enabled}
          onChange={(event) =>
            void save({ medical_disclaimer_position: event.target.value }, "Đã đổi chỗ đặt câu lưu ý y khoa")
          }
          options={[
            { value: "last_comment", label: "Cuối bình luận cuối" },
            { value: "caption", label: "Trong caption (cách cũ, AI tự viết)" },
          ]}
        />
        <Input.TextArea
          aria-label="Nội dung câu lưu ý y khoa"
          value={text}
          maxLength={1000}
          autoSize={{ minRows: 2, maxRows: 6 }}
          disabled={busy || !topic.medical_disclaimer_enabled}
          onChange={(event) => setText(event.target.value)}
        />
        <Flex gap={8}>
          <Button
            type="primary"
            disabled={busy || text.trim() === topic.medical_disclaimer_text.trim()}
            onClick={() => void save({ medical_disclaimer_text: text }, "Đã lưu câu lưu ý y khoa")}
          >
            Lưu câu lưu ý
          </Button>
        </Flex>
      </Flex>
    </Card>
  );
}
