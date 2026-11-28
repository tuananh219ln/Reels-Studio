"use client";

import { MutedOutlined, SoundOutlined } from "@ant-design/icons";
import { Button, Flex, Slider, Tooltip, Typography } from "antd";
import { useSyncExternalStore } from "react";

/** How loud this browser plays the app's media: the listener's own level, never the video's mix, so it changes
 * nothing that is rendered or posted. Kept per browser, shared by every player on the page. */
export type Listen = { level: number; muted: boolean };

const KEY = "reels.listenVolume";
const DEFAULT: Listen = { level: 1, muted: false };

let current: Listen = DEFAULT;
let loaded = false;
const listeners = new Set<() => void>();

function load(): Listen {
  if (!loaded) {
    loaded = true;
    try {
      const saved = JSON.parse(window.localStorage.getItem(KEY) ?? "null");
      if (saved && typeof saved.level === "number" && typeof saved.muted === "boolean") {
        current = { level: Math.min(Math.max(saved.level, 0), 1), muted: saved.muted };
      }
    } catch {
      // A browser that refuses storage plays at full level.
    }
  }
  return current;
}

export function setListen(next: Listen) {
  current = { level: Math.min(Math.max(next.level, 0), 1), muted: next.muted };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    // A browser that refuses storage just forgets the level.
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The listener's level and mute, and the factor to multiply a player's own volume by (0 when muted). */
export function useListen(): Listen & { factor: number } {
  const listen = useSyncExternalStore(subscribe, load, () => DEFAULT);
  return { ...listen, factor: listen.muted ? 0 : listen.level };
}

/** The level and mute last set, for a player's own controls to compare with before it calls setListen. */
export function listenNow(): Listen {
  return load();
}

// What each key adds to the level, in percent.
const KEY_STEPS: Record<string, number> = {
  ArrowLeft: -1,
  ArrowDown: -1,
  ArrowRight: 1,
  ArrowUp: 1,
  PageDown: -10,
  PageUp: 10,
  Home: -100,
  End: 100,
};

/** A speaker button that mutes and unmutes, and a slider from 0 to 100 %. */
export default function ListenVolume({ width = 120 }: { width?: number }) {
  const { level, muted } = useListen();
  const silent = muted || level === 0;
  const percent = silent ? 0 : Math.round(level * 100);
  // The slider's keys are handled here, not by the slider: its own handling leaves one more update pending after each
  // key, and with keys coming faster than React finishes them (an arrow held down) the page gave up and crashed
  // ("Maximum update depth exceeded").
  function onKey(event: React.KeyboardEvent) {
    const step = KEY_STEPS[event.key];
    if (step === undefined) return;
    event.preventDefault();
    event.stopPropagation();
    const now = listenNow();
    // The level as stored, which may be ahead of what is drawn while keys come quickly.
    const from = now.muted ? 0 : Math.round(now.level * 100);
    setListen({ level: (from + step) / 100, muted: false });
  }
  return (
    <Flex align="center" gap={6} data-testid="listen-volume">
      <Tooltip title={silent ? "Bật tiếng" : "Tắt tiếng"}>
        <Button
          size="small"
          type="text"
          aria-label={silent ? "Bật tiếng" : "Tắt tiếng"}
          icon={silent ? <MutedOutlined /> : <SoundOutlined />}
          onClick={() => setListen({ level: level === 0 ? 1 : level, muted: !silent })}
        />
      </Tooltip>
      <div onKeyDown={onKey}>
        <Slider
          ariaLabelForHandle="Âm lượng nghe"
          keyboard={false}
          min={0}
          max={100}
          value={percent}
          onChange={(value) => setListen({ level: value / 100, muted: false })}
          // No tooltip: while open it leaves an update pending after every redraw, which a held key or a drag piles
          // up the same way. The level is written beside the slider instead.
          tooltip={{ open: false }}
          style={{ width, margin: "0 6px" }}
        />
      </div>
      <Typography.Text type="secondary" data-testid="listen-level" style={{ width: 36, fontSize: 12 }}>
        {percent}%
      </Typography.Text>
    </Flex>
  );
}
