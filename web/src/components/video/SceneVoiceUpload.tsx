"use client";

import { DeleteOutlined, UploadOutlined } from "@ant-design/icons";
import { App, Button, Flex, Popconfirm, Tag, Typography } from "antd";
import { useRef, useState } from "react";
import { MAX_MUSIC_BYTES } from "@/components/music/TrackModal";
import { api, errorMessage, upload, type SceneData, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

/**
 * "Tải giọng lên": an MP3 made outside the app (another voice, a recording) read as the scene's narration instead of
 * the voice service. The voice text stays for the captions; only the video's maker changes it (the API says so).
 */
export default function SceneVoiceUpload({ scene }: { scene: SceneData }) {
  const editor = useEditor();
  const { message } = App.useApp();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const frozen = editor.locked || editor.readOnly;

  async function run(action: () => Promise<VideoDetail>, success: string) {
    setBusy(true);
    try {
      editor.onSaved(await action());
      message.success(success);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function chosen(file: File | undefined) {
    if (input.current) {
      input.current.value = "";
    }
    if (!file) {
      return;
    }
    if (file.size > MAX_MUSIC_BYTES) {
      message.error("File giọng đọc quá 20 MB, hãy chọn file nhỏ hơn");
      return;
    }
    void run(() => upload<VideoDetail>(`/scenes/${scene.id}/voice`, file), "Đã dùng file giọng đọc cho cảnh");
  }

  return (
    <Flex wrap gap="4px 8px" align="center" data-testid="scene-voice-upload">
      <input
        ref={input}
        type="file"
        accept="audio/mpeg,.mp3"
        aria-label="Tải file giọng đọc cho cảnh"
        hidden
        onChange={(event) => chosen(event.target.files?.[0])}
      />
      {scene.voice_custom && (
        <Tag color="purple" style={{ marginInlineEnd: 0, maxWidth: "100%" }} data-testid="scene-voice-custom">
          <Typography.Text ellipsis style={{ maxWidth: 220, fontSize: 12 }}>
            Giọng tải lên: {scene.voice_name ?? "file MP3"}
          </Typography.Text>
        </Tag>
      )}
      <Button
        size="small"
        icon={<UploadOutlined />}
        disabled={frozen}
        loading={busy}
        onClick={() => input.current?.click()}
      >
        {scene.voice_custom ? "Thay file giọng" : "Tải giọng lên"}
      </Button>
      {scene.voice_custom && (
        <Popconfirm
          title="Bỏ file giọng đọc?"
          description="Lần render sau cảnh đọc lại bằng giọng của cảnh hoặc của video."
          okText="Bỏ file"
          cancelText="Giữ"
          onConfirm={() => run(() => api<VideoDetail>(`/scenes/${scene.id}/voice`, "DELETE"), "Đã bỏ file giọng đọc")}
        >
          <Button size="small" icon={<DeleteOutlined />} disabled={frozen || busy}>
            Bỏ file
          </Button>
        </Popconfirm>
      )}
    </Flex>
  );
}
