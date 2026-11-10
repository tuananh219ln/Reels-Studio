"use client";

import { App, Button, Card, Radio, Typography } from "antd";
import { useState } from "react";
import { errorMessage, type GroupVideoMode, type KnowledgeTopic } from "@/lib/api";
import EditHistory from "@/components/EditHistory";
import { GROUP_VIDEO_MODES, groupVideoModeLabel, videoModeLabel } from "@/components/video/videoModes";

type Update = (body: Partial<KnowledgeTopic>) => Promise<KnowledgeTopic>;

/**
 * "Kiểu video của nhóm": the mode every new video of the group takes, however it is made (the web, the team's AI, the
 * semi-automatic round, the assistant through MCP), unless one is picked for that video. "Xen kẽ theo ngày" goes by
 * the Vietnam calendar day: odd days "Video xuyên suốt", even days "Slide ảnh".
 */
export default function GroupVideoModeCard({ topic, update }: { topic: KnowledgeTopic; update: Update }) {
  const { message } = App.useApp();
  const [mode, setMode] = useState<GroupVideoMode>(topic.video_mode);
  const [seen, setSeen] = useState(topic.video_mode);
  const [busy, setBusy] = useState(false);
  // A new saved value (another tab, "Lịch sử") replaces the choice shown.
  if (seen !== topic.video_mode) {
    setSeen(topic.video_mode);
    setMode(topic.video_mode);
  }

  async function save() {
    setBusy(true);
    try {
      const saved = await update({ video_mode: mode });
      setMode(saved.video_mode);
      message.success("Đã lưu kiểu video của nhóm");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Kiểu video của nhóm"
      size="small"
      extra={
        <EditHistory
          entityType="knowledge_topic"
          entityId={topic.id}
          field="video_mode"
          title="Kiểu video của nhóm"
          kind="value"
          show={(saved) => groupVideoModeLabel((String(saved) || "slides") as GroupVideoMode)}
          current={groupVideoModeLabel(topic.video_mode)}
        />
      }
    >
      <Typography.Paragraph type="secondary">
        Mọi video tạo mới trong nhóm theo kiểu này: tạo trên web, bằng AI của nhóm, bán tự động và trợ lý qua MCP. Chọn
        riêng kiểu cho một video lúc tạo vẫn được. Video đã có không đổi.
      </Typography.Paragraph>
      <Radio.Group
        aria-label="Kiểu video của nhóm"
        value={mode}
        onChange={(event) => setMode(event.target.value as GroupVideoMode)}
        options={GROUP_VIDEO_MODES.map((item) => ({ value: item.value, label: item.label }))}
        style={{ display: "flex", flexDirection: "column", gap: 8 }}
      />
      {topic.video_mode === "alternate" && (
        <Typography.Text type="secondary" style={{ display: "block", marginTop: 8, fontSize: 12 }}>
          Hôm nay (giờ Việt Nam): {videoModeLabel(topic.video_mode_today)}
        </Typography.Text>
      )}
      <Button
        type="primary"
        loading={busy}
        disabled={mode === topic.video_mode}
        style={{ marginTop: 12 }}
        onClick={save}
      >
        Lưu kiểu video
      </Button>
    </Card>
  );
}
