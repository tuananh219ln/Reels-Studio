"use client";

import { Alert, App, Button, Popconfirm } from "antd";
import { useState } from "react";
import { useMe } from "@/components/MeContext";
import { api, errorMessage, type VideoDetail } from "@/lib/api";
import { narration } from "@/lib/narration";
import { useEditor } from "./AutoSaveField";

/**
 * Says that scenes read an MP3 a member (or their Claude, through MCP) uploaded: the voice, speed and text no longer
 * change what those scenes say. Its maker can drop every file at once.
 */
export function UploadedVoiceNote({ video, disabled }: { video: VideoDetail; disabled: boolean }) {
  const { message } = App.useApp();
  const { me } = useMe();
  const editor = useEditor();
  const [busy, setBusy] = useState(false);
  const { uploaded, service } = narration(video);
  if (uploaded.length === 0) return null;

  /** One scene after another: each answer is the whole video, so the page follows along. */
  async function removeAll() {
    setBusy(true);
    try {
      for (const scene of uploaded) {
        editor.onSaved(await api<VideoDetail>(`/scenes/${scene.id}/voice`, "DELETE"));
      }
      message.success("Đã bỏ các file giọng đọc");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Alert
      type={service.length ? "warning" : "info"}
      showIcon
      data-testid="uploaded-voice-note"
      title={
        service.length
          ? `Trộn 2 nguồn giọng: ${uploaded.length} cảnh đọc MP3 tải lên, ${service.length} cảnh đọc bằng dịch vụ`
          : `Lời đọc là MP3 tải lên (${uploaded.length} cảnh)`
      }
      description={
        <>
          {service.length
            ? "Giọng và tốc độ bên dưới chỉ áp dụng cho cảnh đọc bằng dịch vụ."
            : "Dịch vụ, giọng và tốc độ không áp dụng cho file tải lên."}{" "}
          Chữ lời đọc của cảnh có file chỉ dùng làm phụ đề; muốn đổi giọng thì thay hoặc bỏ file ở cảnh.
          {video.created_by_id === me.id && (
            <div style={{ marginTop: 8 }}>
              <Popconfirm
                title={`Bỏ ${uploaded.length} file giọng đọc?`}
                description="Lần render sau các cảnh này đọc lại bằng giọng của cảnh hoặc của video (tốn ký tự)."
                okText="Bỏ tất cả"
                cancelText="Giữ"
                onConfirm={removeAll}
                disabled={disabled}
              >
                <Button size="small" disabled={disabled} loading={busy}>
                  Bỏ tất cả file, dùng giọng dịch vụ
                </Button>
              </Popconfirm>
            </div>
          )}
        </>
      }
    />
  );
}

/** The voice and speed a video had, and the narration already made with them. */
export type SpeechBefore = {
  voiceId: string;
  speed: number;
  /** Scenes whose narration was made, with its length and whether the scene has a voice of its own. */
  made: { id: number; seconds: number; ownVoice: boolean }[];
  /** The video's length then. */
  total: number;
};

export function speechBefore(video: VideoDetail): SpeechBefore {
  const scenes = [...(video.title_scene ? [video.title_scene] : []), ...video.scenes];
  return {
    voiceId: video.options.voice_id,
    speed: video.options.voice_speed,
    made: narration(video).service.flatMap((scene) =>
      scene.voice_seconds === null
        ? []
        : [{ id: scene.id, seconds: scene.voice_seconds, ownVoice: Boolean(scene.voice_id) }],
    ),
    total: scenes.reduce((sum, scene) => sum + scene.fitted_seconds, 0),
  };
}

/** What changing the voice or speed costs: which narration the next render makes again, with the way back. */
export function SpeechRemakeNote({
  video,
  before,
  disabled,
  onUndo,
}: {
  video: VideoDetail;
  before: SpeechBefore;
  disabled: boolean;
  onUndo: () => void;
}) {
  const voiceChanged = video.options.voice_id !== before.voiceId;
  const speedChanged = video.options.voice_speed !== before.speed;
  // A scene with a voice of its own keeps it when the video's voice changes, but not its speed.
  const remade = before.made.filter((scene) => speedChanged || (voiceChanged && !scene.ownVoice));
  if (remade.length === 0) return null;
  const what = voiceChanged && speedChanged ? "giọng và tốc độ" : voiceChanged ? "giọng" : "tốc độ";
  // An estimate: the narration made, read at the new speed.
  const total =
    before.total +
    before.made.reduce((sum, scene) => sum + scene.seconds * (before.speed / video.options.voice_speed - 1), 0);
  return (
    <Alert
      type="warning"
      showIcon
      data-testid="speech-remake-note"
      title={`Đã đổi ${what}: lần render sau tạo lại lời đọc cho ${remade.length} cảnh (tốn ký tự)${
        speedChanged ? `, video dài khoảng ${Math.round(total)} giây` : ""
      }.`}
      action={
        <Button size="small" disabled={disabled} onClick={onUndo}>
          Hoàn tác
        </Button>
      }
    />
  );
}
