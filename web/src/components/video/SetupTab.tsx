"use client";

import { App, Collapse, Flex, Typography } from "antd";
import Link from "next/link";
import { useState } from "react";
import { COLORS } from "@/app/theme";
import { useMe } from "@/components/MeContext";
import { api, errorMessage, type VideoDefaults, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";
import LogoCard from "./LogoCard";
import MusicCard from "./MusicCard";
import { useTextStyleName } from "./TextStyleCards";
import { AudioSettings, MotionSettings, TextSettings, motionSummary, textSummary } from "./VideoSettings";

type Section = "audio" | "music" | "motion" | "text";
// "Âm thanh" is open the first time; the member's own choice is remembered after that.
const FIRST_OPEN: Section[] = ["audio"];
const storageKey = (memberId: number) => `video-setup-open:${memberId}`;

/** The sections the member left open last time, in this browser; the first-time set when nothing is stored. */
function readOpen(memberId: number): Section[] {
  try {
    const stored = JSON.parse(window.localStorage.getItem(storageKey(memberId)) ?? "null") as unknown;
    return Array.isArray(stored) ? (stored.filter((key) => typeof key === "string") as Section[]) : FIRST_OPEN;
  } catch {
    return FIRST_OPEN;
  }
}

function writeOpen(memberId: number, open: Section[]) {
  try {
    window.localStorage.setItem(storageKey(memberId), JSON.stringify(open));
  } catch {
    // Private windows and blocked storage: the panels still open and close, just not remembered.
  }
}

/**
 * The video's own settings ("Thiết lập" tab). Each change saves at once; later defaults never replace them. "Logo"
 * comes first, in two rows; the other groups open and close, each showing its current values in one line while
 * closed, so they are read without opening.
 */
export default function SetupTab({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const { me } = useMe();
  const editor = useEditor();
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<Section[]>(() => (typeof window === "undefined" ? FIRST_OPEN : readOpen(me.id)));
  const values = { ...video.options, voice_enabled: video.voice_enabled };
  const styleName = useTextStyleName(values);

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
  const audioSummary = video.voice_enabled ? `Có giọng đọc, ${video.options.voice_volume}%` : "Không giọng đọc";
  const musicSummary = video.music ? `${video.music.name ?? "Nhạc tải lên"}, ${video.music_volume}%` : "Chưa có nhạc";
  const panel = (key: Section, title: string, summary: string, children: React.ReactNode) => ({
    key,
    // Every panel stays mounted once drawn, so a closed one keeps what is being typed and its file inputs.
    forceRender: true,
    label: (
      <Flex gap={8} align="baseline" style={{ minWidth: 0 }}>
        <Typography.Text strong style={{ flex: "none" }}>
          {title}
        </Typography.Text>
        {/* The current values, so a closed group is read without opening it. */}
        {!open.includes(key) && (
          <Typography.Text type="secondary" ellipsis style={{ fontSize: 12, minWidth: 0 }} data-testid="setup-summary">
            {summary}
          </Typography.Text>
        )}
      </Flex>
    ),
    children,
  });

  return (
    <Flex vertical gap={12} data-testid="setup-tab">
      <LogoCard video={video} disabled={disabled} onSave={(options) => void save({ options })} />
      <Collapse
        size="small"
        expandIconPlacement="end"
        activeKey={open}
        onChange={(keys) => {
          const next = (Array.isArray(keys) ? keys : [keys]) as Section[];
          setOpen(next);
          writeOpen(me.id, next);
        }}
        style={{ background: COLORS.surface }}
        items={[
          panel(
            "audio",
            "Âm thanh",
            audioSummary,
            <AudioSettings values={values} onChange={change} disabled={disabled} bare />,
          ),
          panel("music", "Nhạc nền", musicSummary, <MusicCard video={video} />),
          panel(
            "motion",
            "Hình ảnh",
            motionSummary(video.options),
            <MotionSettings values={values} onChange={change} disabled={disabled} bare />,
          ),
          panel(
            "text",
            "Chữ & phụ đề",
            textSummary(values, styleName),
            <TextSettings values={values} onChange={change} disabled={disabled} bare />,
          ),
        ]}
      />
      {/* At the foot of the panel, in view however far its groups are scrolled. */}
      <Flex
        vertical
        gap={2}
        data-testid="setup-notes"
        style={{
          position: "sticky",
          bottom: 0,
          zIndex: 1,
          padding: "8px 0 4px",
          background: COLORS.layout,
          borderTop: `1px solid ${COLORS.border}`,
        }}
      >
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Đổi giọng hoặc tốc độ thì lần render sau tạo lại lời đọc (tốn ký tự).
        </Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Video mới lấy mặc định của người tạo. Sửa mặc định của bạn ở{" "}
          <Link prefetch={false} href="/settings/defaults">
            Cài đặt › Thiết lập mặc định
          </Link>
        </Typography.Text>
      </Flex>
    </Flex>
  );
}
