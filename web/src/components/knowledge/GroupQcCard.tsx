"use client";

import { App, Button, Card, Flex, InputNumber, Switch, Typography } from "antd";
import { useState } from "react";
import { errorMessage, type KnowledgeTopic, type QcConfig, type QcRange } from "@/lib/api";
import { useLeaveGuard } from "@/lib/unsaved";
import EditHistory from "@/components/EditHistory";

type Update = (body: Partial<KnowledgeTopic>) => Promise<KnowledgeTopic>;

/** The app's defaults (api qc_config.defaults): saving them is the same as setting nothing. */
const DEFAULTS: QcConfig = {
  title_required: true,
  total_seconds: { min: 20, max: 55 },
  scene_count: { min: 5, max: 7 },
  channel_seconds: { min: 20, max: 40 },
};

type RangeField = "total_seconds" | "scene_count" | "channel_seconds";

const RANGES: { field: RangeField; label: string; unit: string; hint: string; max: number; step: number }[] = [
  {
    field: "total_seconds",
    label: "Độ dài kịch bản",
    unit: "giây",
    hint: "Tổng số giây các cảnh; ngoài khoảng này thì cảnh báo vàng. Tối đa cứng 150 giây cho mọi nhóm.",
    max: 150,
    step: 1,
  },
  {
    field: "scene_count",
    label: "Số cảnh nội dung",
    unit: "cảnh",
    hint: "Không tính cảnh tiêu đề.",
    max: 30,
    step: 1,
  },
  {
    field: "channel_seconds",
    label: "Độ dài MP4",
    unit: "giây",
    hint: "Kênh nhắm khoảng này; video đã render cũng được chấm lại theo ngưỡng mới.",
    max: 300,
    step: 1,
  },
];

/**
 * "QC & duyệt": the group's yellow ranges and whether approving its videos asks for a title (api qc_config.py). Left
 * as the app's defaults, the group checks as every group did before; the loudness target is the same for every group.
 */
export default function GroupQcCard({ topic, update }: { topic: KnowledgeTopic; update: Update }) {
  const { message } = App.useApp();
  const [saved, setSaved] = useState<QcConfig>(topic.qc_config);
  const [draft, setDraft] = useState<QcConfig>(saved);
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  useLeaveGuard(() => dirty);

  function setRange(field: RangeField, side: keyof QcRange, value: number | null) {
    setDraft((current) => ({ ...current, [field]: { ...current[field], [side]: value ?? 0 } }));
  }

  async function save(body: QcConfig) {
    setBusy(true);
    try {
      const next = (await update({ qc_config: body })).qc_config;
      setSaved(next);
      setDraft(next);
      message.success(body === DEFAULTS ? "Nhóm đã về ngưỡng mặc định của app" : "Đã lưu QC & duyệt");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="QC & duyệt"
      size="small"
      extra={
        <EditHistory
          entityType="knowledge_topic"
          entityId={topic.id}
          field="qc_config"
          title="QC & duyệt"
          kind="value"
          show={(value) => (value ? "Đã đặt riêng" : "Mặc định của app")}
          current={topic.qc_config_set ? "Đã đặt riêng" : "Mặc định của app"}
        />
      }
    >
      <Flex vertical gap={12} data-testid="qc-config">
        <Typography.Text type="secondary">
          {topic.qc_config_set
            ? "Nhóm đang dùng ngưỡng riêng."
            : "Nhóm đang dùng ngưỡng mặc định của app (bắt tiêu đề, kịch bản 20–55 giây, 5–7 cảnh, MP4 20–40 giây)."}{" "}
          Âm lượng chuẩn −14 LUFS chung cho mọi nhóm.
        </Typography.Text>
        <Flex align="center" gap={8}>
          <Switch
            aria-label="Bắt tiêu đề khi duyệt"
            checked={draft.title_required}
            onChange={(checked) => setDraft((current) => ({ ...current, title_required: checked }))}
          />
          <Typography.Text>Bắt tiêu đề khi duyệt</Typography.Text>
        </Flex>
        <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: -8 }}>
          Tắt cho format không có chữ tiêu đề trên màn hình (vd. Threads: tiêu đề nằm trong thẻ OP).
        </Typography.Text>
        {RANGES.map((range) => (
          <div key={range.field}>
            <Typography.Text strong>{range.label}</Typography.Text>
            <Flex align="center" gap={8} wrap style={{ marginTop: 4 }}>
              <InputNumber
                aria-label={`${range.label} tối thiểu`}
                min={0}
                max={range.max}
                step={range.step}
                value={draft[range.field].min}
                onChange={(value) => setRange(range.field, "min", value)}
              />
              <span>đến</span>
              <InputNumber
                aria-label={`${range.label} tối đa`}
                min={0}
                max={range.max}
                step={range.step}
                value={draft[range.field].max}
                onChange={(value) => setRange(range.field, "max", value)}
              />
              <span>{range.unit}</span>
            </Flex>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {range.hint}
            </Typography.Text>
          </div>
        ))}
        <Flex gap={8} wrap>
          <Button type="primary" loading={busy} disabled={!dirty} onClick={() => save(draft)}>
            Lưu QC & duyệt
          </Button>
          <Button disabled={busy || !topic.qc_config_set} onClick={() => save(DEFAULTS)}>
            Về mặc định của app
          </Button>
        </Flex>
      </Flex>
    </Card>
  );
}
