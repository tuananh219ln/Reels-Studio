"use client";

import { Typography } from "antd";
import { useRef, useState } from "react";
import { COLORS } from "@/app/theme";

const MIN = 1;
const MAX = 10;
const tenth = (value: number) => Math.round(value * 10) / 10;
const shown = (value: number) => value.toLocaleString("vi-VN", { maximumFractionDigits: 1 });

type Part = { start: number; seconds: number };

/**
 * Under the phone, for a scene with a clip: the whole clip as a bar and the part the scene plays as a window on it.
 * Dragging the window moves the start; its ends set the start and the scene's seconds (at the clip's speed). The
 * phone shows the frame under the pointer while dragging, and the part is saved when the pointer is let go.
 */
export default function ClipTrim({
  clip,
  seconds,
  editable,
  onSeek,
  onCommit,
}: {
  clip: { seconds: number; start: number; speed: number };
  /** The scene's own seconds: the window is that long at the clip's speed. */
  seconds: number;
  editable: boolean;
  onSeek: (time: number) => void;
  onCommit: (part: Part) => void;
}) {
  const bar = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState<Part | null>(null);
  const part = draft ?? { start: clip.start, seconds };
  const speed = clip.speed || 1;
  const span = Math.min(clip.seconds - part.start, part.seconds * speed);
  const percent = (value: number) => `${(value / clip.seconds) * 100}%`;

  function drag(event: React.PointerEvent, handle: "move" | "left" | "right") {
    if (!editable) return;
    event.preventDefault();
    event.stopPropagation();
    const width = bar.current?.getBoundingClientRect().width ?? 1;
    const perSecond = width / clip.seconds;
    const x0 = event.clientX;
    const from = { start: clip.start, seconds };
    const end0 = from.start + from.seconds * speed;
    let last = from;
    const move = (moveEvent: PointerEvent) => {
      const delta = (moveEvent.clientX - x0) / perSecond;
      let next: Part;
      if (handle === "move") {
        const start = Math.min(Math.max(0, from.start + delta), Math.max(0, clip.seconds - from.seconds * speed));
        next = { start: tenth(start), seconds: from.seconds };
        onSeek(next.start);
      } else if (handle === "left") {
        // The end stays; the start moves within what leaves the scene 1–10 s long.
        const start = Math.min(Math.max(0, from.start + delta, end0 - MAX * speed), end0 - MIN * speed);
        next = { start: tenth(start), seconds: tenth((end0 - start) / speed) };
        onSeek(next.start);
      } else {
        const end = Math.min(clip.seconds, Math.max(end0 + delta, from.start + MIN * speed));
        next = { start: from.start, seconds: Math.min(MAX, tenth((end - from.start) / speed)) };
        onSeek(from.start + next.seconds * speed);
      }
      last = next;
      setDraft(next);
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setDraft(null);
      onSeek(last.start);
      if (last.start !== from.start || last.seconds !== from.seconds) {
        onCommit(last);
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  const handle = (side: "left" | "right") => (
    <span
      role="slider"
      aria-label={side === "left" ? "Đầu đoạn clip" : "Cuối đoạn clip"}
      aria-valuenow={side === "left" ? part.start : part.start + span}
      aria-valuemin={0}
      aria-valuemax={clip.seconds}
      onPointerDown={(event) => drag(event, side)}
      style={{
        position: "absolute",
        top: 0,
        bottom: 0,
        [side]: -4,
        width: 8,
        borderRadius: 3,
        background: COLORS.primary,
        cursor: editable ? "ew-resize" : "default",
        touchAction: "none",
      }}
    />
  );

  return (
    <div style={{ width: "100%" }} data-testid="clip-trim">
      <div
        ref={bar}
        style={{
          position: "relative",
          height: 28,
          borderRadius: 6,
          background: COLORS.muted,
          border: `1px solid ${COLORS.border}`,
        }}
      >
        <div
          aria-label="Đoạn clip của cảnh"
          onPointerDown={(event) => drag(event, "move")}
          style={{
            position: "absolute",
            top: -1,
            bottom: -1,
            left: percent(part.start),
            width: percent(span),
            border: `2px solid ${COLORS.primary}`,
            borderRadius: 6,
            background: "rgba(194, 65, 12, 0.12)",
            cursor: editable ? "grab" : "default",
            touchAction: "none",
          }}
        >
          {editable && handle("left")}
          {editable && handle("right")}
        </div>
      </div>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Đoạn clip từ {shown(part.start)} đến {shown(part.start + span)} giây (clip dài {shown(clip.seconds)} giây
        {speed !== 1 ? `, tốc độ ${shown(speed)}×` : ""}), cảnh dài {shown(part.seconds)} giây
      </Typography.Text>
    </div>
  );
}
