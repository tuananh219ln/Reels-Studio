"use client";

import { App, Card, Flex, Switch, Typography } from "antd";
import { useState } from "react";
import { errorMessage, type KnowledgeTopic } from "@/lib/api";
import EditHistory from "@/components/EditHistory";

type Update = (body: Partial<KnowledgeTopic>) => Promise<KnowledgeTopic>;

/**
 * "Không dùng cảnh có người": the group's scenes show no faces or bodies; hands at work are fine. Assistants read it
 * from each video of the group (MCP) and pick their photos and clips by it.
 */
export default function GroupNoPeopleCard({ topic, update }: { topic: KnowledgeTopic; update: Update }) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);

  async function toggle(checked: boolean) {
    setBusy(true);
    try {
      await update({ no_people: checked });
      message.success(checked ? "Đã bật: không dùng cảnh có người" : "Đã tắt: cảnh có người được dùng");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Cảnh có người"
      size="small"
      extra={
        <EditHistory
          entityType="knowledge_topic"
          entityId={topic.id}
          field="no_people"
          title="Không dùng cảnh có người"
          kind="value"
          show={(saved) => (saved ? "Bật" : "Tắt")}
          current={topic.no_people ? "Bật" : "Tắt"}
        />
      }
    >
      <Flex gap={12} align="flex-start">
        <Switch
          aria-label="Không dùng cảnh có người"
          checked={topic.no_people}
          loading={busy}
          disabled={busy}
          onChange={(checked) => void toggle(checked)}
          style={{ marginTop: 2 }}
        />
        <Flex vertical gap={4}>
          <Typography.Text strong>Không dùng cảnh có người</Typography.Text>
          <Typography.Text type="secondary">
            Ảnh và clip của các cảnh không có mặt, thân người hay người nói trước camera; bàn tay đang gắp, múc, cắt,
            rót thì được. Trợ lý qua MCP chọn tư liệu theo công tắc này.
          </Typography.Text>
        </Flex>
      </Flex>
    </Card>
  );
}
