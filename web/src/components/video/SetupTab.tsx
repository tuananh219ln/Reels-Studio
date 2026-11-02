"use client";

import { App, Button, Flex, Popconfirm, Typography } from "antd";
import Link from "next/link";
import { useState } from "react";
import { api, errorMessage, type VideoDefaults, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";
import MusicCard from "./MusicCard";
import { AudioSettings, MotionSettings, TextSettings } from "./VideoSettings";

/** The video's own settings ("Thiết lập" tab). Each change saves at once; the team's defaults can replace them. */
export default function SetupTab({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const editor = useEditor();
  const [busy, setBusy] = useState(false);
  const values = { ...video.options, voice_enabled: video.voice_enabled };

  async function save(body: object) {
    setBusy(true);
    try {
      editor.onSaved(await api<VideoDetail>(`/videos/${video.id}`, "PATCH", body));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function change({ voice_enabled, music_volume, ...options }: Partial<VideoDefaults>) {
    void save({
      ...(voice_enabled !== undefined ? { voice_enabled } : {}),
      ...(music_volume !== undefined ? { music_volume } : {}),
      ...(Object.keys(options).length ? { options } : {}),
    });
  }

  const disabled = editor.locked || editor.readOnly || busy;
  return (
    <Flex vertical gap={16}>
      <AudioSettings values={values} onChange={change} disabled={disabled} />
      <MusicCard video={video} />
      <MotionSettings values={values} onChange={change} disabled={disabled} />
      <TextSettings values={values} onChange={change} disabled={disabled} />
      <Flex wrap gap={8} align="center">
        <Popconfirm
          title="Lấy toàn bộ thiết lập theo mặc định nhóm?"
          description="Giọng đọc, âm lượng, chuyển cảnh, kiểu chữ và phụ đề của video này sẽ đổi theo mặc định."
          okText="Lấy theo mặc định"
          cancelText="Huỷ"
          onConfirm={() => save({ reset_options: true })}
        >
          <Button disabled={disabled}>Lấy theo mặc định nhóm</Button>
        </Popconfirm>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Sửa mặc định ở <Link href="/settings/defaults">Cài đặt › Thiết lập mặc định</Link>
        </Typography.Text>
      </Flex>
    </Flex>
  );
}
