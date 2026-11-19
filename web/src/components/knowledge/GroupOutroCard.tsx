"use client";

import { App, Card, Flex, Switch, Typography } from "antd";
import { useState } from "react";
import { errorMessage, type KnowledgeTopic } from "@/lib/api";
import EditHistory from "@/components/EditHistory";

type Update = (body: Partial<KnowledgeTopic>) => Promise<KnowledgeTopic>;

/**
 * "Cảnh kết Theo dõi & Chia sẻ": the group's new videos (every way of making one) end on the shared follow-and-share
 * motion scene, which takes the place of the script's own closing call to action (api outro.py).
 */
export default function GroupOutroCard({ topic, update }: { topic: KnowledgeTopic; update: Update }) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);

  async function toggle(checked: boolean) {
    setBusy(true);
    try {
      await update({ outro_cta: checked });
      message.success(checked ? "Đã bật cảnh kết Theo dõi & Chia sẻ" : "Đã tắt cảnh kết Theo dõi & Chia sẻ");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Cảnh kết"
      size="small"
      extra={
        <EditHistory
          entityType="knowledge_topic"
          entityId={topic.id}
          field="outro_cta"
          title="Cảnh kết Theo dõi & Chia sẻ"
          kind="value"
          show={(saved) => (saved ? "Bật" : "Tắt")}
          current={topic.outro_cta ? "Bật" : "Tắt"}
        />
      }
    >
      <Flex gap={12} align="flex-start">
        <Switch
          aria-label="Cảnh kết Theo dõi & Chia sẻ"
          checked={topic.outro_cta}
          loading={busy}
          disabled={busy}
          onChange={(checked) => void toggle(checked)}
          style={{ marginTop: 2 }}
        />
        <Flex vertical gap={4}>
          <Typography.Text strong>Cảnh kết Theo dõi & Chia sẻ</Typography.Text>
          <Typography.Text type="secondary">
            Video mới của nhóm tự kết bằng cảnh động 4,5 giây “Thấy hữu ích? Theo dõi & Chia sẻ” có lời đọc và tiếng
            Ting, thay cho cảnh kêu gọi cuối của kịch bản. Video đã có không đổi; muốn bỏ thì xoá cảnh đó trên video.
          </Typography.Text>
        </Flex>
      </Flex>
    </Card>
  );
}
