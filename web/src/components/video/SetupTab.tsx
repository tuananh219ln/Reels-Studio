"use client";

import { App, Button, Flex, Popconfirm, Typography } from "antd";
import Link from "next/link";
import { useState } from "react";
import { COLORS } from "@/app/theme";
import { api, errorMessage, type VideoDefaults, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";
import MusicCard from "./MusicCard";
import { AudioSettings, MotionSettings, TextSettings } from "./VideoSettings";

const SECTIONS = [
  { key: "audio", label: "Âm thanh" },
  { key: "music", label: "Nhạc nền" },
  { key: "motion", label: "Hình ảnh" },
  { key: "text", label: "Chữ & phụ đề" },
] as const;
type Section = (typeof SECTIONS)[number]["key"];

/** The video's own settings ("Thiết lập" tab). Each change saves at once; the team's defaults can replace them. */
export default function SetupTab({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const editor = useEditor();
  const [busy, setBusy] = useState(false);
  const values = { ...video.options, voice_enabled: video.voice_enabled };
  const anchor = (key: Section) => `setup-${key}-${video.id}`;

  /** Scrolls the side panel alone to a group (the scenes stay where they are); a phone scrolls the page. */
  function jump(key: Section) {
    const target = document.getElementById(anchor(key));
    const panel = target?.closest<HTMLElement>("[data-side-panel]");
    if (!target) {
      return;
    }
    if (panel && panel.scrollHeight > panel.clientHeight) {
      const offset = target.getBoundingClientRect().top - panel.getBoundingClientRect().top - 44;
      panel.scrollBy({ top: offset, behavior: "smooth" });
    } else {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

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
      {/* The four groups are long together: a row that jumps to one, kept in view while the panel scrolls. */}
      <Flex
        wrap
        gap={6}
        data-testid="setup-sections"
        style={{ position: "sticky", top: 0, zIndex: 2, padding: "4px 0 8px", background: COLORS.layout }}
      >
        {SECTIONS.map((section) => (
          <Button key={section.key} size="small" onClick={() => jump(section.key)}>
            {section.label}
          </Button>
        ))}
      </Flex>
      <div id={anchor("audio")} style={{ scrollMarginTop: 44 }}>
        <AudioSettings values={values} onChange={change} disabled={disabled} />
      </div>
      <div id={anchor("music")} style={{ scrollMarginTop: 44 }}>
        <MusicCard video={video} />
      </div>
      <div id={anchor("motion")} style={{ scrollMarginTop: 44 }}>
        <MotionSettings values={values} onChange={change} disabled={disabled} />
      </div>
      <div id={anchor("text")} style={{ scrollMarginTop: 44 }}>
        <TextSettings values={values} onChange={change} disabled={disabled} />
      </div>
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
