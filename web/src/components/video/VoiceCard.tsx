"use client";

import { App, Card, Flex, Switch, Typography } from "antd";
import { useState } from "react";
import { api, errorMessage, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

/** Narration on or off for the whole video; each scene's voice text is edited on its scene card. */
export default function VoiceCard({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const editor = useEditor();
  const [busy, setBusy] = useState(false);

  async function toggle(enabled: boolean) {
    setBusy(true);
    try {
      editor.onSaved(await api<VideoDetail>(`/videos/${video.id}`, "PATCH", { voice_enabled: enabled }));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Giọng đọc" size="small">
      <Flex vertical gap={8}>
        <Flex gap={8} align="center">
          <Switch
            aria-label="Đọc lời bằng giọng Adam"
            checked={video.voice_enabled}
            loading={busy}
            disabled={editor.locked}
            onChange={toggle}
          />
          <Typography.Text>Đọc lời từng cảnh bằng giọng Adam (ElevenLabs)</Typography.Text>
        </Flex>
        <Typography.Text type="secondary">
          Lời đọc được tạo khi render, chỉ tạo lại khi lời đọc của cảnh thay đổi. Cảnh có lời đọc dài hơn số giây sẽ tự
          kéo dài cho vừa.
        </Typography.Text>
      </Flex>
    </Card>
  );
}
