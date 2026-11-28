"use client";

import { App, Button, Card, Flex, InputNumber, Segmented, Switch, Typography } from "antd";
import { useState } from "react";
import { errorMessage, type GroupVideoLook, type KnowledgeTopic, type VideoOptions } from "@/lib/api";
import EditHistory from "@/components/EditHistory";
import LibraryPicker from "@/components/music/LibraryPicker";
import { AudioRest, MotionSettings, motionSummary, type SettingsValues } from "@/components/video/VideoSettings";

type Update = (body: Partial<KnowledgeTopic>) => Promise<KnowledgeTopic>;
type Track = KnowledgeTopic["video_look_track"];
/** The group's music: each maker's own, one library track, or none. */
type Music = "maker" | "track" | "none";

// What the card sets (api video_options.GROUP_VIDEO_FIELDS), in the order it shows them.
const FIELDS = [
  "transition",
  "motion",
  "zoom",
  "voice_enabled",
  "voice_speed",
  "voice_volume",
  "voice_pause",
  "ducking",
  "music_volume",
  "music_track_id",
  "music_start",
] as const;
const TITLE = "Chuyển động & âm thanh của nhóm";
const MAX_MUSIC_START = 600; // api video_options.MAX_MUSIC_START

function pick(look: GroupVideoLook): GroupVideoLook {
  return Object.fromEntries(FIELDS.filter((name) => look[name] !== undefined).map((name) => [name, look[name]]));
}

function same(first: GroupVideoLook | null, second: GroupVideoLook | null): boolean {
  return JSON.stringify(first ? pick(first) : null) === JSON.stringify(second ? pick(second) : null);
}

const musicOf = (look: GroupVideoLook): Music =>
  look.music_track_id === undefined ? "maker" : look.music_track_id === null ? "none" : "track";

/** A few words for a saved value, for its history: "Mờ dần, Zoom vào, Vừa; đọc 1,05×; nhạc 12%". */
function describe(look: GroupVideoLook | null): string {
  if (!look) return "Theo người tạo video";
  const words: string[] = [];
  if (look.transition && look.motion && look.zoom) {
    words.push(motionSummary({ transition: look.transition, motion: look.motion, zoom: look.zoom }));
  }
  if (look.voice_enabled === false) words.push("không đọc lời");
  else if (look.voice_speed) words.push(`đọc ${look.voice_speed.toLocaleString("vi-VN")}×`);
  if (look.voice_volume !== undefined) words.push(`giọng ${look.voice_volume}%`);
  if (look.music_volume !== undefined) words.push(`nhạc ${look.music_volume}%`);
  if (look.music_track_id === null) words.push("không nhạc nền");
  else if (look.music_track_id) words.push(`bài nhạc #${look.music_track_id} từ giây ${look.music_start ?? 0}`);
  return words.join("; ") || "Thiết lập riêng";
}

/**
 * "Chuyển động & âm thanh của nhóm": how the group's new videos move and sound, and their background music, over their
 * maker's defaults (Cài đặt › Thiết lập mặc định). Off, each maker's own; on, it starts from the member's own and saves
 * every field shown; the music only once a track or "Không nhạc" is chosen.
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
  const [track, setTrack] = useState<Track>(topic.video_look_track);
  const [picking, setPicking] = useState(false);
  const [seen, setSeen] = useState(JSON.stringify(topic.video_look));
  const [busy, setBusy] = useState(false);
  // A new saved value (another tab, "Lịch sử") replaces what the card shows.
  const key = JSON.stringify(topic.video_look);
  if (seen !== key) {
    setSeen(key);
    setOwn(topic.video_look !== null);
    setLook({ ...start, ...(topic.video_look ?? {}) });
    setTrack(topic.video_look_track);
  }
  const changed = !same(own ? look : null, topic.video_look);
  const music = musicOf(look);

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

  const change = (changes: GroupVideoLook) => setLook((current) => ({ ...current, ...changes }));

  function chooseMusic(next: Music) {
    if (next === "track") {
      // A track is chosen by picking one; closing the window leaves the choice as it was.
      setPicking(true);
      return;
    }
    // `undefined` leaves the key out of what is saved: the maker's own music.
    change({ music_track_id: next === "none" ? null : undefined, music_start: undefined });
  }

  // The shared sections read a video's whole settings; they show only the fields above.
  const values = { ...(look as VideoOptions), voice_enabled: look.voice_enabled ?? true } as SettingsValues;
  values.music_volume = look.music_volume;

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
          Chuyển cảnh, chuyển động, giọng đọc, âm lượng và nhạc nền cho video mới của nhóm. Chỉnh riêng trên từng video
          vẫn được; video đã có không đổi.
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
            <Flex align="center" gap={8}>
              <Switch
                checked={values.voice_enabled}
                onChange={(voice_enabled) => change({ voice_enabled })}
                aria-label="Đọc lời từng cảnh"
              />
              <Typography.Text>Đọc lời từng cảnh</Typography.Text>
            </Flex>
            <AudioRest values={values} onChange={change} showMusicVolume />
            <Flex vertical gap={8} data-testid="group-music">
              <Typography.Text strong>Nhạc nền</Typography.Text>
              <Segmented
                aria-label="Nhạc nền của nhóm"
                value={music}
                options={[
                  { value: "maker", label: "Theo người tạo" },
                  { value: "track", label: "Chọn bài" },
                  { value: "none", label: "Không nhạc" },
                ]}
                onChange={(next) => chooseMusic(next as Music)}
              />
              {music === "track" && (
                <>
                  {track ? (
                    <>
                      <Typography.Text data-testid="group-music-name">{track.name}</Typography.Text>
                      <audio src={track.url} controls preload="none" style={{ width: "100%" }} />
                      {track.claimed_on_youtube && (
                        <Typography.Text type="warning">
                          Bài này đã bị claim trên YouTube: video mới đang dùng nhạc của người tạo. Hãy chọn bài khác.
                        </Typography.Text>
                      )}
                    </>
                  ) : (
                    <Typography.Text type="warning">
                      Bài nhạc đã bị xoá khỏi thư viện: video mới đang dùng nhạc của người tạo. Hãy chọn bài khác.
                    </Typography.Text>
                  )}
                  <Flex align="center" gap={8} wrap>
                    <Button onClick={() => setPicking(true)}>Đổi bài</Button>
                    <Typography.Text>Bắt đầu từ giây</Typography.Text>
                    <InputNumber
                      aria-label="Bắt đầu từ giây"
                      min={0}
                      max={MAX_MUSIC_START}
                      step={1}
                      value={look.music_start ?? 0}
                      onChange={(second) => change({ music_start: second ?? 0 })}
                    />
                  </Flex>
                </>
              )}
              {music === "maker" && (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Mỗi video dùng nhạc mặc định của người tạo nó.
                </Typography.Text>
              )}
            </Flex>
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
      <LibraryPicker
        open={picking}
        busy={false}
        onClose={() => setPicking(false)}
        onPick={(picked) => {
          setTrack({ id: picked.id, name: picked.name, url: picked.url });
          change({ music_track_id: picked.id, music_start: 0 });
          setPicking(false);
        }}
      />
    </Card>
  );
}
