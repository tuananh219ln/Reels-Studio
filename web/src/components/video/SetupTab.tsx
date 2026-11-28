"use client";

import { isPcShopee } from "@/lib/pcShopee";
import { Alert, App, Collapse, Flex, Switch, Typography } from "antd";
import Link from "next/link";
import { useState } from "react";
import { COLORS } from "@/app/theme";
import { useMe } from "@/components/MeContext";
import { api, errorMessage, formatDateTime, type VideoDefaults, type VideoDetail } from "@/lib/api";
import { narration } from "@/lib/narration";
import { useEditor } from "./AutoSaveField";
import LayoutCard from "./LayoutCard";
import LogoCard from "./LogoCard";
import MusicCard from "./MusicCard";
import { SpeechRemakeNote, UploadedVoiceNote, speechBefore, type SpeechBefore } from "./NarrationNotes";
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
  // The voice and speed before they were first changed here, to say what the change costs and to put them back.
  const [before, setBefore] = useState<SpeechBefore | null>(null);
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
    if (before === null && (options.voice_id !== undefined || options.voice_speed !== undefined)) {
      setBefore(speechBefore(video));
    }
    void save({
      ...(voice_enabled !== undefined ? { voice_enabled } : {}),
      ...(music_volume !== undefined ? { music_volume } : {}),
      ...(Object.keys(options).length ? { options } : {}),
    });
  }

  const disabled = editor.locked || editor.readOnly || busy;
  const { uploaded, service } = narration(video);
  const uploadedOnly = uploaded.length > 0 && service.length === 0;
  const voiceSources =
    uploaded.length === 0
      ? "Có giọng đọc"
      : uploadedOnly
        ? `MP3 tải lên ${uploaded.length} cảnh`
        : `Trộn giọng: MP3 ${uploaded.length}, dịch vụ ${service.length} cảnh`;
  const audioSummary = video.voice_enabled ? `${voiceSources}, ${video.options.voice_volume}%` : "Không giọng đọc";
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
      <MediaKeep
        video={video}
        disabled={editor.readOnly || busy}
        onChange={(keep_media) => void save({ keep_media })}
      />
      <LogoCard video={video} disabled={disabled} onSave={(options) => void save({ options })} />
      <LayoutCard video={video} disabled={disabled} onSave={(options) => void save({ options })} />
      <Collapse
        size="small"
        className="setup-groups"
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
            <Flex vertical gap={10}>
              <UploadedVoiceNote video={video} disabled={disabled} />
              <AudioSettings values={values} onChange={change} disabled={disabled} bare uploadedOnly={uploadedOnly} />
              {before && (
                <SpeechRemakeNote
                  video={video}
                  before={before}
                  disabled={disabled}
                  onUndo={() => {
                    setBefore(null);
                    void save({ options: { voice_id: before.voiceId, voice_speed: before.speed } });
                  }}
                />
              )}
            </Flex>,
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
            <TextSettings
              values={values}
              onChange={change}
              disabled={disabled}
              bare
              textHold={isPcShopee(video.knowledge_topic)}
            />,
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

/**
 * "Giữ media": a posted video's photos, clips and narration are deleted by the worker some days after its last post
 * (its MP4s and thumbnail stay). This keeps them, so the video can still be copied, shuffled and rendered.
 */
function MediaKeep({
  video,
  disabled,
  onChange,
}: {
  video: VideoDetail;
  disabled: boolean;
  onChange: (keep: boolean) => void;
}) {
  if (video.media_cleaned_at) {
    return (
      <Alert
        type="info"
        showIcon
        data-testid="media-cleaned"
        title={`Media đã được dọn ngày ${formatDateTime(video.media_cleaned_at).slice(0, 10)}`}
        description="Ảnh, clip và lời đọc đã xoá; MP4 và số liệu vẫn còn. Video này không render, nhân bản hay xáo cảnh được nữa."
      />
    );
  }
  return (
    <Flex vertical gap={4} data-testid="media-keep">
      <Flex gap={8} align="center">
        <Switch
          size="small"
          checked={video.keep_media}
          disabled={disabled}
          onChange={onChange}
          aria-label="Giữ media"
        />
        <Typography.Text strong>Giữ media</Typography.Text>
      </Flex>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Video đã đăng quá hạn sẽ bị dọn ảnh, clip và lời đọc để nhẹ ổ (MP4 và số liệu vẫn giữ). Bật để giữ lại, nếu bạn
        còn muốn nhân bản hay xáo cảnh video này.
      </Typography.Text>
      {video.media_due_at && !video.keep_media && (
        <Typography.Text type="warning" style={{ fontSize: 12 }} data-testid="media-due">
          Media sẽ được dọn từ {formatDateTime(video.media_due_at).slice(0, 10)}.
        </Typography.Text>
      )}
    </Flex>
  );
}
