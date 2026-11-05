"use client";

import { DeleteOutlined, PlusOutlined, SoundOutlined } from "@ant-design/icons";
import { Button, Flex, InputNumber, Popconfirm, Segmented, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import type { SceneData, SceneSound } from "@/lib/api";
import { MUSIC_LEVELS, SOUND_VOLUMES, SOUNDS, soundGain, soundLabel, soundUrl } from "./sounds";

const seconds = (value: number) => value.toLocaleString("vi-VN", { maximumFractionDigits: 1 });

/** Plays a sound once, at the listener's level (a browser plays at most full volume). */
function hear(url: string, gain: number) {
  const audio = new Audio(url);
  audio.volume = Math.min(1, Math.max(0, gain));
  void audio.play().catch(() => undefined);
}

/**
 * "Âm thanh" in the tools column: every sound effect, heard with "Nghe" and added to the scene shown at the playhead
 * with "Thêm"; and, when the video has music, the second of the song it starts from.
 */
export function SoundTools({
  scene,
  editable,
  musicStart,
  hasMusic,
  listen,
  onAdd,
  onMusicStart,
}: {
  scene: SceneData | undefined;
  editable: boolean;
  musicStart: number;
  hasMusic: boolean;
  /** The listener's own level (ListenVolume). */
  listen: number;
  onAdd: (sound: string) => void;
  onMusicStart: (seconds: number) => void;
}) {
  // Started from the saved second; the studio keys this panel on it, so a save (or "Hoàn tác") resets it.
  const [start, setStart] = useState<number | null>(musicStart);
  const commit = () => {
    if (start !== null && start !== musicStart) onMusicStart(start);
  };
  return (
    <Flex vertical gap={12} data-testid="sound-tools">
      <Typography.Text strong>Âm thanh</Typography.Text>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Âm do máy tạo, không vướng bản quyền. “Thêm” đặt âm vào cảnh đang xem, tại chỗ đầu phát.
      </Typography.Text>
      <Flex vertical gap={4} role="list" aria-label="Âm thanh">
        {SOUNDS.map((item) => (
          <Flex key={item.value} role="listitem" align="center" gap={6}>
            <Typography.Text style={{ flex: 1, fontSize: 13 }}>{item.label}</Typography.Text>
            <Button
              size="small"
              type="text"
              aria-label={`Nghe ${item.label}`}
              icon={<SoundOutlined />}
              onClick={() => hear(soundUrl(item.value), listen)}
            />
            <Button
              size="small"
              aria-label={`Thêm âm ${item.label}`}
              icon={<PlusOutlined />}
              disabled={!editable || !scene}
              onClick={() => onAdd(item.value)}
            >
              Thêm
            </Button>
          </Flex>
        ))}
      </Flex>
      {hasMusic && (
        <Flex vertical gap={4}>
          <Typography.Text strong style={{ fontSize: 13 }}>
            Bài nhạc bắt đầu từ giây
          </Typography.Text>
          <InputNumber
            aria-label="Bài nhạc bắt đầu từ giây"
            min={0}
            max={600}
            step={0.5}
            precision={1}
            value={start}
            disabled={!editable}
            onChange={setStart}
            onBlur={commit}
            onPressEnter={commit}
            suffix="giây"
            style={{ width: 140 }}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Bỏ qua đoạn dạo đầu của bài: video mở đầu bằng đoạn nhạc từ giây này.
          </Typography.Text>
        </Flex>
      )}
    </Flex>
  );
}

/**
 * "Âm thanh" in "Chỉnh cảnh N": the music's level during this scene, and its sound effects, each with its second,
 * its level and "Xoá"; every change saved at once and undone with Ctrl+Z.
 */
export function SoundList({
  scene,
  editable,
  hasMusic,
  onMusicLevel,
  onPatch,
  onRemove,
}: {
  scene: SceneData;
  editable: boolean;
  hasMusic: boolean;
  onMusicLevel: (level: string | null) => void;
  onPatch: (sound: SceneSound, label: string, body: Record<string, unknown>) => void;
  onRemove: (sound: SceneSound) => void;
}) {
  return (
    <Flex vertical gap={10} data-testid="sound-list">
      {hasMusic && (
        <Flex vertical gap={4}>
          <Typography.Text strong style={{ fontSize: 13 }}>
            Nhạc ở cảnh này
          </Typography.Text>
          <Segmented
            size="small"
            aria-label="Nhạc ở cảnh này"
            value={scene.music_level ?? "video"}
            disabled={!editable}
            options={MUSIC_LEVELS.map(({ value, label }) => ({ value, label }))}
            onChange={(value) => onMusicLevel(value === "video" ? null : String(value))}
          />
        </Flex>
      )}
      {scene.sounds.length === 0 ? (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Cảnh chưa có âm nào. Thêm ở “Âm thanh” bên trái.
        </Typography.Text>
      ) : (
        scene.sounds.map((sound) => (
          <SoundRow
            key={`${sound.id}-${sound.start}`}
            sound={sound}
            sceneSeconds={scene.fitted_seconds}
            editable={editable}
            onPatch={(label, body) => onPatch(sound, label, body)}
            onRemove={() => onRemove(sound)}
          />
        ))
      )}
    </Flex>
  );
}

function SoundRow({
  sound,
  sceneSeconds,
  editable,
  onPatch,
  onRemove,
}: {
  sound: SceneSound;
  sceneSeconds: number;
  editable: boolean;
  onPatch: (label: string, body: Record<string, unknown>) => void;
  onRemove: () => void;
}) {
  const [start, setStart] = useState<number | null>(sound.start);
  const commit = () => {
    if (start !== null && start !== sound.start) onPatch("đổi giây của âm", { start });
  };
  return (
    <Flex
      vertical
      gap={6}
      data-testid="sound-row"
      style={{ border: "1px solid #e7e8ea", borderRadius: 6, padding: "6px 8px" }}
    >
      <Flex align="center" gap={8}>
        <Typography.Text strong style={{ flex: 1, fontSize: 12 }}>
          {soundLabel(sound.sound)}
        </Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          từ {seconds(sound.start)}s
        </Typography.Text>
        <Button
          size="small"
          type="text"
          aria-label={`Nghe ${soundLabel(sound.sound)}`}
          icon={<SoundOutlined />}
          onClick={() => hear(sound.url, soundGain(sound.volume))}
        />
        <Popconfirm
          title="Xoá âm này?"
          okText="Xoá"
          cancelText="Huỷ"
          okButtonProps={{ danger: true }}
          disabled={!editable}
          onConfirm={onRemove}
        >
          <Button size="small" type="text" danger aria-label="Xoá âm" icon={<DeleteOutlined />} disabled={!editable} />
        </Popconfirm>
      </Flex>
      <Flex gap={8} align="center" wrap>
        <InputNumber
          aria-label="Giây bắt đầu của âm"
          size="small"
          min={0}
          max={Math.max(0, sceneSeconds - 0.1)}
          step={0.1}
          precision={1}
          value={start}
          disabled={!editable}
          onChange={setStart}
          onBlur={commit}
          onPressEnter={commit}
          prefix="từ"
          suffix="s"
          style={{ width: 100 }}
        />
        <Segmented
          size="small"
          aria-label="Mức âm"
          value={sound.volume}
          disabled={!editable}
          options={SOUND_VOLUMES.map(({ value, label }) => ({ value, label }))}
          onChange={(volume) => onPatch("đổi mức âm", { volume })}
        />
      </Flex>
    </Flex>
  );
}

/**
 * Plays the scene's sound effects in the preview, each when the clock passes its second while playing (the render
 * mixes them the same way). Nothing on screen.
 */
export function SoundStage({
  sounds,
  elapsed,
  playing,
  listen,
}: {
  sounds: SceneSound[];
  elapsed: () => number;
  playing: boolean;
  listen: number;
}) {
  const current = useRef({ sounds, elapsed, listen });
  useEffect(() => {
    current.current = { sounds, elapsed, listen };
  });
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = current.current.elapsed();
    const tick = () => {
      const { sounds: list, elapsed: at, listen: level } = current.current;
      const now = at();
      for (const sound of list) {
        if (last < sound.start && sound.start <= now) hear(sound.url, soundGain(sound.volume) * level);
      }
      last = now;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing]);
  return null;
}
