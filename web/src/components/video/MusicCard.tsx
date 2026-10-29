"use client";

import { DeleteOutlined, UploadOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Popconfirm, Slider, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { api, errorMessage, upload, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

const MAX_MUSIC_BYTES = 20 * 1024 * 1024;

/** Optional background music: one MP3 per video and its volume; without it the video is silent. */
export default function MusicCard({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const editor = useEditor();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [volume, setVolume] = useState(video.music_volume);
  const [volumeError, setVolumeError] = useState<string | null>(null);
  // The slider shows what the member chose until every volume save has finished; only then does it follow
  // the saved value again (a teammate's change arrives through polling).
  const touched = useRef(false);
  const latest = useRef(video.music_volume);
  const saved = useRef(video.music_volume);
  const queue = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    saved.current = video.music_volume;
    if (!touched.current) {
      setVolume(video.music_volume);
    }
  }, [video.music_volume]);

  function saveVolume(value: number) {
    touched.current = true;
    latest.current = value;
    setVolumeError(null);
    // One save at a time, always with the latest value, so an older value can never land last.
    queue.current = queue.current.then(async () => {
      const sent = latest.current;
      try {
        const result = await api<VideoDetail>(`/videos/${video.id}`, "PATCH", { music_volume: sent });
        if (latest.current === sent) {
          touched.current = false;
          editor.onSaved(result);
        }
      } catch (err) {
        // Only the latest choice decides what is shown: an older failed save is superseded by a newer one.
        if (latest.current === sent) {
          touched.current = false;
          setVolume(saved.current);
          setVolumeError(`${errorMessage(err)} — âm lượng vẫn là ${saved.current}%`);
        }
      }
    });
    editor.track(queue.current);
  }

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
      message.error("File nhạc quá 20 MB, hãy chọn file nhỏ hơn");
      return;
    }
    void run(() => upload<VideoDetail>(`/videos/${video.id}/music`, file), "Đã lưu nhạc");
  }

  return (
    <Card title="Nhạc nền" size="small">
      <input ref={input} type="file" accept="audio/mpeg,.mp3" hidden aria-label="Tải nhạc MP3 lên"
        onChange={(event) => chosen(event.target.files?.[0])} />
      {video.music ? (
        <Flex vertical gap={8}>
          <Typography.Text data-testid="music-name">{video.music.name}</Typography.Text>
          <audio key={video.music.url} src={video.music.url} controls preload="none" style={{ width: "100%" }} />
          <Flex wrap gap={8}>
            <Button icon={<UploadOutlined />} disabled={editor.locked || busy} onClick={() => input.current?.click()}>
              Thay nhạc
            </Button>
            <Popconfirm title="Gỡ nhạc? Video render sau sẽ im lặng." okText="Gỡ nhạc" cancelText="Huỷ"
              onConfirm={() => run(() => api<VideoDetail>(`/videos/${video.id}/music`, "DELETE"), "Đã gỡ nhạc")}>
              <Button danger icon={<DeleteOutlined />} disabled={editor.locked || busy}>
                Gỡ nhạc
              </Button>
            </Popconfirm>
          </Flex>
          <Typography.Text strong>Âm lượng: {volume}%</Typography.Text>
          <Slider
            aria-label="Âm lượng nhạc"
            min={0}
            max={100}
            value={volume}
            disabled={editor.locked}
            onChange={(value) => {
              touched.current = true;
              setVolume(value);
            }}
            onChangeComplete={saveVolume}
          />
          {volumeError && <Typography.Text type="danger">{volumeError}</Typography.Text>}
        </Flex>
      ) : (
        <Flex vertical gap={8}>
          <Typography.Text type="secondary">
            Chưa có nhạc: video render ra im lặng. Có thể chọn nhạc trong TikTok hoặc Facebook khi đăng (xem gợi ý
            nhạc), hoặc tải lên một file MP3 (tối đa 20 MB).
          </Typography.Text>
          <Button icon={<UploadOutlined />} disabled={editor.locked || busy} onClick={() => input.current?.click()}>
            Tải nhạc MP3 lên
          </Button>
        </Flex>
      )}
    </Card>
  );
}
