"use client";

import { App, Button, Card, Flex, Switch, Typography } from "antd";
import { useState } from "react";
import { errorMessage, type GroupVideoLook, type KnowledgeTopic, type VideoOptions } from "@/lib/api";
import EditHistory from "@/components/EditHistory";
import { AudioRest, MotionSettings, motionSummary, type SettingsValues } from "@/components/video/VideoSettings";

type Update = (body: Partial<KnowledgeTopic>) => Promise<KnowledgeTopic>;

// What the card sets (api video_options.GROUP_VIDEO_FIELDS), in the order it shows them.
const FIELDS = [
  "transition",
  "motion",
  "zoom",
  "voice_speed",
  "voice_volume",
  "voice_pause",
  "ducking",
  "music_volume",
] as const;
const TITLE = "Chuyển động & âm thanh của nhóm";

function pick(look: GroupVideoLook): GroupVideoLook {
  return Object.fromEntries(FIELDS.filter((name) => look[name] !== undefined).map((name) => [name, look[name]]));
}

function same(first: GroupVideoLook | null, second: GroupVideoLook | null): boolean {
  return JSON.stringify(first ? pick(first) : null) === JSON.stringify(second ? pick(second) : null);
}

/** A few words for a saved value, for its history: "Mờ dần, Zoom vào, Vừa; đọc 1,05×; nhạc 12%". */
function describe(look: GroupVideoLook | null): string {
  if (!look) return "Theo người tạo video";
  const words: string[] = [];
  if (look.transition && look.motion && look.zoom) {
    words.push(motionSummary({ transition: look.transition, motion: look.motion, zoom: look.zoom }));
  }
  if (look.voice_speed) words.push(`đọc ${look.voice_speed.toLocaleString("vi-VN")}×`);
  if (look.voice_volume !== undefined) words.push(`giọng ${look.voice_volume}%`);
  if (look.music_volume !== undefined) words.push(`nhạc ${look.music_volume}%`);
  return words.join("; ") || "Thiết lập riêng";
}

/**
 * "Chuyển động & âm thanh của nhóm": how the group's new videos move and sound, over their maker's defaults
 * (Cài đặt › Thiết lập mặc định). Off, each maker's own; on, it starts from the member's own and saves every field.
 */
export default function GroupVideoLookCard({
  topic,
  start,
  update,
}: {
  topic: KnowledgeTopic;
  /** Where the group's own settings start: the member's own defaults. */
  start: GroupVideoLook;
  update: Update;
}) {
  const { message } = App.useApp();
  const [own, setOwn] = useState(topic.video_look !== null);
  const [look, setLook] = useState<GroupVideoLook>({ ...start, ...(topic.video_look ?? {}) });
  const [seen, setSeen] = useState(JSON.stringify(topic.video_look));
  const [busy, setBusy] = useState(false);
  // A new saved value (another tab, "Lịch sử") replaces what the card shows.
  const key = JSON.stringify(topic.video_look);
  if (seen !== key) {
    setSeen(key);
    setOwn(topic.video_look !== null);
    setLook({ ...start, ...(topic.video_look ?? {}) });
  }
  const changed = !same(own ? look : null, topic.video_look);

  async function save() {
    setBusy(true);
    try {
      await update({ video_look: own ? pick(look) : null });
      message.success("Đã lưu chuyển động & âm thanh của nhóm");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  // The shared sections read a video's whole settings; they show only the fields above. The narration counts as on,
  // so its speed and level can be set whatever a video later chooses.
  const values = { ...(look as VideoOptions), voice_enabled: true, music_volume: look.music_volume } as SettingsValues;
  const change = (changes: GroupVideoLook) => setLook((current) => ({ ...current, ...changes }));

  return (
    <Card
      title={TITLE}
      size="small"
      data-testid="group-video-look"
      extra={
        <EditHistory
          entityType="knowledge_topic"
          entityId={topic.id}
          field="video_look"
          title={TITLE}
          kind="value"
          show={(saved) => describe((saved || null) as GroupVideoLook | null)}
          current={describe(topic.video_look)}
        />
      }
    >
      <Flex vertical gap={12}>
        <Typography.Text type="secondary">
          Chuyển cảnh, chuyển động, tốc độ đọc và âm lượng cho video mới của nhóm. Chỉnh riêng trên từng video vẫn được;
          video đã có không đổi.
        </Typography.Text>
        <Flex align="center" gap={8}>
          <Switch checked={own} onChange={setOwn} aria-label="Nhóm có chuyển động & âm thanh riêng" />
          <Typography.Text>Nhóm có chuyển động & âm thanh riêng</Typography.Text>
        </Flex>
        <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: -6 }}>
          {own
            ? "Bật: video mới của nhóm theo phần chỉnh bên dưới."
            : "Tắt: video mới theo Thiết lập mặc định của người tạo video."}
        </Typography.Text>
        {own && (
          <>
            <MotionSettings values={values} onChange={change} bare />
            <AudioRest values={values} onChange={change} showMusicVolume />
          </>
        )}
        <Button
          type="primary"
          loading={busy}
          disabled={!changed}
          onClick={() => void save()}
          style={{ alignSelf: "start" }}
        >
          Lưu chuyển động & âm thanh
        </Button>
      </Flex>
    </Card>
  );
}
