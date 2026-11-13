"use client";

import { CustomerServiceOutlined, DeleteOutlined, UploadOutlined } from "@ant-design/icons";
import { App, Button, Checkbox, Flex, Popconfirm, Slider, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import LibraryPicker from "@/components/music/LibraryPicker";
import TrackModal, { MAX_MUSIC_BYTES, type TrackTarget } from "@/components/music/TrackModal";
import { api, errorMessage, upload, type MusicTrack, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

/** Optional background music: one MP3 per video, uploaded or copied from the team library, and its volume;
 * without it the video is silent. The "Nhạc nền" panel of the video's "Thiết lập" tab names it. */
export default function MusicCard({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const editor = useEditor();
  // A running job or the page's view mode: the music cannot change.
  const frozen = editor.locked || editor.readOnly;
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState(false);
  const [saveToLibrary, setSaveToLibrary] = useState(false);
  // Kept as state so it keeps its identity across polls: a new object would reset the modal's form.
  const [newTrack, setNewTrack] = useState<TrackTarget | null>(null);
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

  /** True when the change was saved. */
  async function run(action: () => Promise<VideoDetail>, success: string): Promise<boolean> {
    setBusy(true);
    try {
      editor.onSaved(await action());
      message.success(success);
      return true;
    } catch (err) {
      message.error(errorMessage(err));
      return false;
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
    if (saveToLibrary) {
      setNewTrack({ file });
    } else {
      void run(() => upload<VideoDetail>(`/videos/${video.id}/music`, file), "Đã lưu nhạc");
    }
  }

  async function applyTrack(track: MusicTrack) {
    const saved = await run(
      () => api<VideoDetail>(`/videos/${video.id}/music/from-library`, "POST", { track_id: track.id }),
      `Đã dùng "${track.name}"`,
    );
    if (saved) {
      setPicking(false);
    }
  }

  const sources = (
    <>
      <Flex wrap gap={8}>
        <Button icon={<CustomerServiceOutlined />} disabled={frozen || busy} onClick={() => setPicking(true)}>
          Chọn từ thư viện
        </Button>
        <Button icon={<UploadOutlined />} disabled={frozen || busy} onClick={() => input.current?.click()}>
          {video.music ? "Thay nhạc" : "Tải nhạc MP3 lên"}
        </Button>
      </Flex>
      <Checkbox checked={saveToLibrary} onChange={(event) => setSaveToLibrary(event.target.checked)}>
        Lưu file tải lên vào thư viện nhạc
      </Checkbox>
    </>
  );

  return (
    <div data-testid="music-settings">
      <input
        ref={input}
        type="file"
        accept="audio/mpeg,.mp3"
        hidden
        aria-label="Tải nhạc MP3 lên"
        onChange={(event) => chosen(event.target.files?.[0])}
      />
      {video.music ? (
        <Flex vertical gap={8}>
          <Typography.Text data-testid="music-name">{video.music.name}</Typography.Text>
          <audio key={video.music.url} src={video.music.url} controls preload="none" style={{ width: "100%" }} />
          {sources}
          <Flex wrap gap={8}>
            <Popconfirm
              title="Gỡ nhạc? Video render sau sẽ im lặng."
              okText="Gỡ nhạc"
              cancelText="Huỷ"
              onConfirm={() => run(() => api<VideoDetail>(`/videos/${video.id}/music`, "DELETE"), "Đã gỡ nhạc")}
            >
              <Button danger icon={<DeleteOutlined />} disabled={frozen || busy}>
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
            disabled={frozen}
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
            nhạc), chọn một bài trong thư viện nhạc, hoặc tải lên một file MP3 (tối đa 20 MB).
          </Typography.Text>
          {sources}
        </Flex>
      )}
      <LibraryPicker open={picking} busy={busy} onClose={() => setPicking(false)} onPick={applyTrack} />
      <TrackModal
        target={newTrack}
        onClose={() => setNewTrack(null)}
        onDone={async (track) => {
          setNewTrack(null);
          await applyTrack(track);
        }}
      />
    </div>
  );
}
