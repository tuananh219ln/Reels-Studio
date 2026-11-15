"use client";

import { Tooltip } from "antd";
import { useRef, useState } from "react";
import { useStoredChoice } from "@/lib/storedChoice";

/** The scenes' share of the width when nothing is stored, and what a double click goes back to
 * (docs/decisions/2026-11-14-video-editor-spec.md: scenes 60%, panel 40%). */
export const DEFAULT_SHARE = 0.6;
/** Neither side gets narrower than this: the scene cards and the 440 px the side panel's drawer has. */
export const LEFT_MIN = 420;
export const RIGHT_MIN = 440;
const HANDLE = 20;
// One arrow key press moves the line by this share of the width.
const STEP = 0.02;

function parseShare(stored: string): number {
  const share = Number(stored);
  return Number.isFinite(share) && share > 0 && share < 1 ? share : DEFAULT_SHARE;
}

/** `share` kept so that both sides keep their minimum in a row `width` px wide (handle included). */
function clamp(share: number, width: number): number {
  const room = width - HANDLE;
  if (room <= LEFT_MIN + RIGHT_MIN) return LEFT_MIN / (LEFT_MIN + RIGHT_MIN);
  return Math.min(Math.max(share, LEFT_MIN / room), 1 - RIGHT_MIN / room);
}

/**
 * Two columns with a line between them that the member drags to give one side more room; a double click on it goes
 * back to 60/40, the arrow keys move it too. The share is kept in this browser per member (`storageKey`). The left
 * column scrolls with the page; the right one is whatever `right` lays out (the side panel, its tabs sticky).
 */
export default function ResizableColumns({
  storageKey,
  left,
  right,
}: {
  storageKey: string;
  left: React.ReactNode;
  right: React.ReactNode;
}) {
  const [stored, store] = useStoredChoice(storageKey, String(DEFAULT_SHARE));
  // While dragging the line follows the pointer here; it is stored once, when the pointer lets go.
  const [dragging, setDragging] = useState<number | null>(null);
  const row = useRef<HTMLDivElement>(null);
  const share = dragging ?? parseShare(stored);
  const width = () => row.current?.getBoundingClientRect().width ?? 0;
  const save = (next: number) => store(String(Math.round(clamp(next, width()) * 1000) / 1000));

  function follow(clientX: number) {
    const box = row.current?.getBoundingClientRect();
    if (!box) return;
    setDragging(clamp((clientX - box.left - HANDLE / 2) / (box.width - HANDLE), box.width));
  }

  const percent = Math.round(share * 100);
  return (
    <div
      ref={row}
      data-testid="split-columns"
      data-share={share.toFixed(3)}
      style={{
        display: "grid",
        // Each side keeps its minimum whatever was stored; the shares split what is left.
        gridTemplateColumns: `minmax(${LEFT_MIN}px, ${share}fr) ${HANDLE}px minmax(${RIGHT_MIN}px, ${1 - share}fr)`,
        alignItems: "start",
        // No text gets selected while the line is dragged across it.
        userSelect: dragging === null ? undefined : "none",
      }}
    >
      <div style={{ minWidth: 0 }}>{left}</div>
      <Tooltip title="Kéo để đổi độ rộng hai cột, bấm đúp để về 60/40" placement="right" mouseEnterDelay={0.6}>
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Đổi độ rộng cột cảnh và bảng bên phải"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          tabIndex={0}
          className={`split-handle${dragging === null ? "" : " split-handle--dragging"}`}
          data-testid="split-handle"
          onPointerDown={(event) => {
            event.currentTarget.setPointerCapture(event.pointerId);
            follow(event.clientX);
          }}
          onPointerMove={(event) => dragging !== null && follow(event.clientX)}
          onPointerUp={() => {
            if (dragging !== null) save(dragging);
            setDragging(null);
          }}
          onPointerCancel={() => setDragging(null)}
          onDoubleClick={() => {
            setDragging(null);
            save(DEFAULT_SHARE);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
              event.preventDefault();
              save(share + (event.key === "ArrowLeft" ? -STEP : STEP));
            } else if (event.key === "Home" || event.key === "Enter") {
              event.preventDefault();
              save(DEFAULT_SHARE);
            }
          }}
        >
          <span className="split-handle__grip" />
        </div>
      </Tooltip>
      <div style={{ minWidth: 0 }}>{right}</div>
    </div>
  );
}
