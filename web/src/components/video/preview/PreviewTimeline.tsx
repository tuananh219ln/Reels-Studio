"use client";

import { Tooltip } from "antd";
import { useRef, useState } from "react";
import { COLORS } from "@/app/theme";
import type { SceneData } from "@/lib/api";

const MIN = 1;
const MAX = 10;
/** Pointer travel before a press on a segment becomes a drag that reorders it. */
const DRAG_PX = 6;

const tenth = (value: number) => Math.round(value * 10) / 10;
const shown = (value: number) => value.toLocaleString("vi-VN", { maximumFractionDigits: 1 });

/**
 * The bar under the phone, one segment per scene as long as it plays; the current one fills as it plays. A click jumps
 * to a scene. While editing, a segment's right edge drags its seconds (double-click: back to its narration's length),
 * and a content scene's segment drags along the bar to a new place.
 */
export default function PreviewTimeline({
  scenes,
  current,
  run,
  running,
  editable,
  label,
  onJump,
  onSeconds,
  onFollowVoice,
  onReorder,
}: {
  scenes: SceneData[];
  current: number;
  run: number;
  running: boolean;
  editable: boolean;
  label: (index: number) => string;
  onJump: (index: number) => void;
  onSeconds: (index: number, seconds: number) => void;
  onFollowVoice: (index: number) => void;
  /** The content scenes' ids in their new order. */
  onReorder: (ids: number[]) => void;
}) {
  const bar = useRef<HTMLDivElement>(null);
  // The edge being dragged and the seconds it shows, or the segment being moved and where it would land.
  const [resizing, setResizing] = useState<{ index: number; seconds: number } | null>(null);
  const [moving, setMoving] = useState<{ index: number; to: number } | null>(null);
  const press = useRef<{ x: number; index: number; moved: boolean } | null>(null);
  // A drag that reordered must not also count as a click that jumps to the scene.
  const dragged = useRef(false);

  // While an edge is dragged its segment shows the new seconds, or the narration's length when that is longer.
  const lengths = scenes.map((scene, index) =>
    resizing?.index === index
      ? Math.max(resizing.seconds, scene.fitted_seconds > scene.seconds ? scene.fitted_seconds : 0)
      : scene.fitted_seconds,
  );
  const total = lengths.reduce((sum, value) => sum + value, 0) || 1;
  const firstContent = scenes[0]?.is_title ? 1 : 0;

  function startResize(event: React.PointerEvent, index: number) {
    event.stopPropagation();
    event.preventDefault();
    const width = bar.current?.getBoundingClientRect().width ?? 1;
    const perSecond = width / total;
    const from = scenes[index].seconds;
    const x0 = event.clientX;
    let last = from;
    const move = (moveEvent: PointerEvent) => {
      last = Math.min(MAX, Math.max(MIN, tenth(from + (moveEvent.clientX - x0) / perSecond)));
      setResizing({ index, seconds: last });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setResizing(null);
      if (last !== from) {
        onSeconds(index, last);
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  /** The place a segment dropped at `x` goes to, among the content scenes (the title always opens the video). */
  function landing(x: number): number {
    const rect = bar.current?.getBoundingClientRect();
    if (!rect) return firstContent;
    let edge = rect.left;
    for (let index = 0; index < scenes.length; index++) {
      const width = (lengths[index] / total) * rect.width;
      if (x < edge + width / 2) return Math.max(firstContent, index);
      edge += width;
    }
    return scenes.length - 1;
  }

  function startPress(event: React.PointerEvent, index: number) {
    press.current = { x: event.clientX, index, moved: false };
    dragged.current = false;
    if (!editable || scenes[index].is_title) return;
    const move = (moveEvent: PointerEvent) => {
      const state = press.current;
      if (!state) return;
      if (!state.moved && Math.abs(moveEvent.clientX - state.x) < DRAG_PX) return;
      state.moved = true;
      setMoving({ index, to: landing(moveEvent.clientX) });
    };
    const up = (upEvent: PointerEvent) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      const state = press.current;
      press.current = null;
      setMoving(null);
      if (!state?.moved) return;
      dragged.current = true;
      const to = landing(upEvent.clientX);
      if (to === index) return;
      const ids = scenes.slice(firstContent).map((scene) => scene.id);
      const [picked] = ids.splice(index - firstContent, 1);
      ids.splice(to - firstContent, 0, picked);
      onReorder(ids);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  return (
    <div
      ref={bar}
      style={{ display: "flex", gap: 3, width: "100%", position: "relative" }}
      data-testid="preview-timeline"
    >
      {scenes.map((item, index) => (
        <div
          key={item.id}
          style={{
            flex: lengths[index],
            position: "relative",
            opacity: moving?.index === index ? 0.4 : 1,
            boxShadow:
              moving && moving.to === index && moving.index !== index ? `-3px 0 0 ${COLORS.primary}` : undefined,
          }}
        >
          <button
            type="button"
            aria-label={`Xem ${label(index)}`}
            onPointerDown={(event) => startPress(event, index)}
            onClick={() => {
              if (!dragged.current) onJump(index);
            }}
            style={{
              display: "block",
              width: "100%",
              height: editable ? 10 : 6,
              padding: 0,
              border: 0,
              borderRadius: 3,
              cursor: editable && !item.is_title ? "grab" : "pointer",
              overflow: "hidden",
              background: index < current ? COLORS.primary : COLORS.border,
              touchAction: "none",
            }}
          >
            {index === current && (
              <span
                key={run}
                style={{
                  display: "block",
                  height: "100%",
                  background: COLORS.primary,
                  animationName: "preview-progress",
                  animationDuration: `${item.fitted_seconds}s`,
                  animationTimingFunction: "linear",
                  animationFillMode: "both",
                  animationPlayState: running ? "running" : "paused",
                }}
              />
            )}
          </button>
          {editable && (
            <Tooltip
              open={resizing?.index === index ? true : undefined}
              title={
                resizing?.index === index
                  ? `${shown(resizing.seconds)} giây`
                  : `Kéo để đổi số giây (${shown(item.seconds)}), bấm đúp để khớp lời đọc`
              }
            >
              <span
                role="separator"
                aria-label={`Số giây ${label(index)}`}
                aria-valuenow={item.seconds}
                aria-valuemin={MIN}
                aria-valuemax={MAX}
                data-testid="timeline-edge"
                onPointerDown={(event) => startResize(event, index)}
                onDoubleClick={() => onFollowVoice(index)}
                style={{
                  position: "absolute",
                  right: -5,
                  top: -4,
                  width: 10,
                  height: 18,
                  cursor: "ew-resize",
                  touchAction: "none",
                  zIndex: 1,
                  display: "flex",
                  justifyContent: "center",
                }}
              >
                <span style={{ width: 2, height: "100%", background: COLORS.textSecondary, borderRadius: 1 }} />
              </span>
            </Tooltip>
          )}
        </div>
      ))}
    </div>
  );
}
