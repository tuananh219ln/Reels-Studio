"use client";

import { LockOutlined, UnlockOutlined, ZoomInOutlined, ZoomOutOutlined } from "@ant-design/icons";
import { Button, Flex, Slider, Tooltip, Typography } from "antd";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { COLORS } from "@/app/theme";
import type { SceneData } from "@/lib/api";
import { type Lane, type LockableTrack, laneSpans } from "./tracks";

const MIN = 1;
const MAX = 10;
/** Pointer travel before a press on a segment becomes a drag that reorders it. */
const DRAG_PX = 6;
/** Space before the first scene and after the last, so the playhead's handle is never cut off. */
const PAD = 12;
const ZOOM_MAX = 8;
/**
 * The ruler's label steps, in whole seconds (labels read "00:07"): the first that leaves at least LABEL_PX between two
 * labels is used, with a small tick halfway.
 */
const STEPS = [1, 2, 5, 10, 15, 30, 60];
const LABEL_PX = 56;
const RULER = 22;
const TRACK = 56;
/** The thinner tracks under the scenes (text, narration, captions, music) and the gap between tracks. */
const LANE = 24;
const GAP = 4;
/** The column of track names at the timeline's left. */
const NAMES = 84;

const LANE_LOOK: Record<Lane["key"], { background: string; color: string }> = {
  text: { background: "#fde7c8", color: "#7c3d00" },
  layers: { background: "#ffd6ec", color: "#8a0a4b" },
  sounds: { background: "#c9f2dd", color: "#0b5a32" },
  voice: { background: "#cfe3ff", color: "#0b3d91" },
  captions: { background: "#fff3b0", color: "#5c4a00" },
  music: { background: "#ddd5f7", color: "#3b2a7a" },
};

const tenth = (value: number) => Math.round(value * 10) / 10;
const shown = (value: number) => value.toLocaleString("vi-VN", { maximumFractionDigits: 1 });

/** "00:07" on the ruler; "00:07,4" with tenths for the playhead. */
export function clockLabel(value: number, tenths = false): string {
  const whole = Math.max(0, value);
  const minutes = Math.floor(whole / 60);
  const rest = whole - minutes * 60;
  const secs = tenths ? Math.floor(rest * 10) / 10 : Math.floor(rest);
  const [int, frac] = secs.toFixed(tenths ? 1 : 0).split(".");
  return `${String(minutes).padStart(2, "0")}:${int.padStart(2, "0")}${tenths ? `,${frac}` : ""}`;
}

/**
 * The studio's timeline under the phone, laid out like a video editor's: a ruler in seconds, the scenes' track (one
 * segment per scene as long as it plays, its picture repeated along it), and under it the tracks of what plays with
 * them: the on-screen text, the narration, the captions and the music. A playhead follows the preview and can be
 * dragged or clicked to any second, and a zoom goes from the whole video to a few seconds across. A click on any
 * block plays its scene. While editing, a segment's right edge drags its seconds (double-click: back to its
 * narration's length), and a content scene's segment drags along the track to a new place. The scenes' and the
 * text's tracks can be locked so a stray drag changes neither.
 */
export default function PreviewTimeline({
  scenes,
  current,
  editable,
  label,
  lanes,
  musicName,
  locks,
  onLock,
  position,
  controls,
  onSeek,
  onJump,
  onSeconds,
  onFollowVoice,
  onReorder,
}: {
  scenes: SceneData[];
  current: number;
  /** The scenes' track can be changed (the page is in edit mode and the track is not locked). */
  editable: boolean;
  label: (index: number) => string;
  /** The tracks under the scenes, in order (tracks.ts). */
  lanes: Lane[];
  musicName: string | null;
  locks: Record<LockableTrack, boolean>;
  onLock: (track: LockableTrack) => void;
  /** Where the preview is, in seconds from the video's start; read every frame for the playhead. */
  position: () => number;
  /** The play buttons, shown at the left of the timeline's header. */
  controls?: React.ReactNode;
  /** The playhead dragged or a point of the ruler clicked: show that second, paused. */
  onSeek: (seconds: number) => void;
  onJump: (index: number) => void;
  onSeconds: (index: number, seconds: number) => void;
  onFollowVoice: (index: number) => void;
  /** The content scenes' ids in their new order. */
  onReorder: (ids: number[]) => void;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);
  const head = useRef<HTMLDivElement>(null);
  const clock = useRef<HTMLSpanElement>(null);
  const [width, setWidth] = useState(0);
  const [zoom, setZoom] = useState(1);
  // The edge being dragged and the seconds it shows, or the segment being moved and where it would land.
  const [resizing, setResizing] = useState<{ index: number; seconds: number } | null>(null);
  const [moving, setMoving] = useState<{ index: number; to: number } | null>(null);
  const press = useRef<{ x: number; index: number; moved: boolean } | null>(null);
  // A drag that reordered must not also count as a click that jumps to the scene.
  const dragged = useRef(false);
  // While the playhead is dragged it follows the pointer, not the preview.
  const scrubbing = useRef<number | null>(null);

  // While an edge is dragged its segment shows the new seconds, or the narration's length when that is longer.
  const lengths = scenes.map((scene, index) =>
    resizing?.index === index
      ? Math.max(resizing.seconds, scene.fitted_seconds > scene.seconds ? scene.fitted_seconds : 0)
      : scene.fitted_seconds,
  );
  const starts = lengths.map((_, index) => lengths.slice(0, index).reduce((sum, value) => sum + value, 0));
  const total = lengths.reduce((sum, value) => sum + value, 0) || 1;
  const firstContent = scenes[0]?.is_title ? 1 : 0;
  // Zoom 1 fits the whole video in the visible width; more spreads it out and the track scrolls.
  const perSecond = (Math.max(width - 2 * PAD, 120) / total) * zoom;
  const step = STEPS.find((value) => value * perSecond >= LABEL_PX) ?? 120;
  const ticks = Array.from({ length: Math.floor(total / step) + 1 }, (_, index) => index * step);
  const xOf = (seconds: number) => PAD + seconds * perSecond;
  const lanesTop = RULER + 4 + TRACK + GAP;
  const height = lanesTop + lanes.length * (LANE + GAP) + 6;

  useLayoutEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const measure = () => setWidth(element.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // The playhead and the clock follow the preview every frame without rendering the timeline again; while playing,
  // the track scrolls to keep the playhead in sight.
  const follow = useRef({ perSecond, total, position });
  useLayoutEffect(() => {
    follow.current = { perSecond, total, position };
  });
  useEffect(() => {
    let frame = 0;
    let last = -1;
    let lastX = -1;
    const tick = () => {
      const { perSecond: scale, total: length, position: at } = follow.current;
      const now = Math.min(length, Math.max(0, scrubbing.current ?? at()));
      const x = PAD + now * scale;
      if (head.current) head.current.style.transform = `translateX(${x}px)`;
      if (clock.current && Math.abs(now - last) >= 0.05) {
        clock.current.textContent = clockLabel(now, true);
        head.current?.setAttribute("aria-valuenow", String(tenth(now)));
        last = now;
      }
      // Only a moving playhead pulls the track along: a member scrolling it while paused keeps their view.
      const view = viewport.current;
      if (view && scrubbing.current === null && x !== lastX && lastX >= 0) {
        if (x < view.scrollLeft || x > view.scrollLeft + view.clientWidth - PAD) {
          view.scrollLeft = Math.max(0, x - PAD * 4);
        }
      }
      lastX = x;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  /** The second under the pointer, kept within the video. */
  function secondAt(clientX: number): number {
    const rect = inner.current?.getBoundingClientRect();
    if (!rect) return 0;
    return Math.min(total, Math.max(0, (clientX - rect.left - PAD) / perSecond));
  }

  /** The ruler or the playhead pressed: the preview follows the pointer until it is let go. */
  function startScrub(event: React.PointerEvent) {
    event.preventDefault();
    event.stopPropagation();
    let frame = 0;
    const to = (clientX: number) => {
      scrubbing.current = secondAt(clientX);
      cancelAnimationFrame(frame);
      const at = scrubbing.current;
      frame = requestAnimationFrame(() => onSeek(at));
    };
    to(event.clientX);
    const move = (moveEvent: PointerEvent) => to(moveEvent.clientX);
    const up = (upEvent: PointerEvent) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      cancelAnimationFrame(frame);
      onSeek(secondAt(upEvent.clientX));
      scrubbing.current = null;
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  function startResize(event: React.PointerEvent, index: number) {
    event.stopPropagation();
    event.preventDefault();
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
    const at = secondAt(x);
    for (let index = 0; index < scenes.length; index++) {
      if (at < starts[index] + lengths[index] / 2) return Math.max(firstContent, index);
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

  /** Zoom keeping the playhead where it is on screen. */
  function zoomTo(next: number) {
    const value = Math.min(ZOOM_MAX, Math.max(1, Math.round(next * 4) / 4));
    const view = viewport.current;
    if (view) {
      const at = position();
      const onScreen = xOf(at) - view.scrollLeft;
      requestAnimationFrame(() => {
        view.scrollLeft = Math.max(0, PAD + at * (perSecond / zoom) * value - onScreen);
      });
    }
    setZoom(value);
  }

  return (
    <Flex vertical gap={6} style={{ width: "100%", minWidth: 0 }} data-testid="preview-timeline">
      <Flex align="center" justify="space-between" gap={12} wrap>
        <Flex align="center" gap={8} wrap>
          {controls}
        </Flex>
        <Typography.Text style={{ fontVariantNumeric: "tabular-nums" }}>
          <span ref={clock} data-testid="preview-time">
            {clockLabel(0, true)}
          </span>
          <Typography.Text type="secondary"> / {clockLabel(total, true)}</Typography.Text>
        </Typography.Text>
        <Flex align="center" gap={4}>
          <Button
            type="text"
            size="small"
            aria-label="Thu nhỏ thanh thời gian"
            icon={<ZoomOutOutlined />}
            disabled={zoom <= 1}
            onClick={() => zoomTo(zoom / 1.5)}
          />
          <Slider
            aria-label="Thu phóng thanh thời gian"
            min={1}
            max={ZOOM_MAX}
            step={0.25}
            value={zoom}
            onChange={zoomTo}
            tooltip={{ formatter: (value) => `${value}×` }}
            style={{ width: 96, margin: "0 6px" }}
          />
          <Button
            type="text"
            size="small"
            aria-label="Phóng to thanh thời gian"
            icon={<ZoomInOutlined />}
            disabled={zoom >= ZOOM_MAX}
            onClick={() => zoomTo(zoom * 1.5)}
          />
        </Flex>
      </Flex>
      <Flex style={{ borderTop: `1px solid ${COLORS.border}`, minWidth: 0 }}>
        {/* The tracks' names, with a lock on those a drag or a key can change. */}
        <div
          data-testid="timeline-tracks"
          style={{ flex: "none", width: NAMES, height, borderRight: `1px solid ${COLORS.border}` }}
        >
          <div style={{ height: RULER + 4 }} />
          <TrackName name="Cảnh" height={TRACK} locked={locks.scene} onLock={() => onLock("scene")} />
          {lanes.map((lane) => (
            <div key={lane.key} style={{ marginTop: GAP }}>
              <TrackName
                name={lane.name}
                height={LANE}
                locked={lane.key === "text" ? locks.text : lane.key === "layers" ? locks.layer : undefined}
                onLock={
                  lane.key === "text" ? () => onLock("text") : lane.key === "layers" ? () => onLock("layer") : undefined
                }
              />
            </div>
          ))}
        </div>
        <div
          ref={viewport}
          data-testid="timeline-viewport"
          style={{
            flex: 1,
            minWidth: 0,
            overflowX: "auto",
            overflowY: "hidden",
            paddingBottom: 6,
          }}
        >
          <div ref={inner} style={{ position: "relative", width: xOf(total) + PAD, height }} data-zoom={zoom}>
            {/* The ruler: a press anywhere on it moves the playhead there, and dragging scrubs. */}
            <div
              data-testid="timeline-ruler"
              onPointerDown={startScrub}
              // Clipped, so the last label never widens the track past the video's end.
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                top: 0,
                height: RULER,
                cursor: "pointer",
                overflow: "hidden",
              }}
            >
              {ticks.map((at) => (
                <span
                  key={at}
                  style={{
                    position: "absolute",
                    left: xOf(at),
                    top: 0,
                    height: RULER,
                    borderLeft: `1px solid ${COLORS.border}`,
                    paddingLeft: 4,
                    fontSize: 11,
                    lineHeight: `${RULER - 6}px`,
                    color: COLORS.textSecondary,
                    fontVariantNumeric: "tabular-nums",
                    userSelect: "none",
                    pointerEvents: "none",
                  }}
                >
                  {clockLabel(at)}
                </span>
              ))}
              {ticks
                .filter((at) => at + step / 2 < total)
                .map((at) => (
                  <span
                    key={`half-${at}`}
                    style={{
                      position: "absolute",
                      left: xOf(at + step / 2),
                      bottom: 0,
                      height: 5,
                      borderLeft: `1px solid ${COLORS.border}`,
                      pointerEvents: "none",
                    }}
                  />
                ))}
            </div>
            {scenes.map((item, index) => {
              const picture = item.preview_url ?? item.frame_url;
              const segmentWidth = Math.max(lengths[index] * perSecond - 2, 4);
              return (
                <div
                  key={item.id}
                  style={{
                    position: "absolute",
                    left: xOf(starts[index]) + 1,
                    top: RULER + 4,
                    width: segmentWidth,
                    height: TRACK,
                    opacity: moving?.index === index ? 0.4 : 1,
                    boxShadow:
                      moving && moving.to === index && moving.index !== index
                        ? `-3px 0 0 ${COLORS.primary}`
                        : undefined,
                  }}
                >
                  <button
                    type="button"
                    aria-label={`Xem ${label(index)}`}
                    aria-current={index === current ? "true" : undefined}
                    onPointerDown={(event) => startPress(event, index)}
                    onClick={() => {
                      if (!dragged.current) onJump(index);
                    }}
                    style={{
                      position: "relative",
                      display: "block",
                      width: "100%",
                      height: "100%",
                      padding: 0,
                      border: 0,
                      borderRadius: 6,
                      cursor: editable && !item.is_title ? "grab" : "pointer",
                      overflow: "hidden",
                      // The scene's picture along it, as an editor's film strip.
                      backgroundColor: "#3a3a3a",
                      backgroundImage: picture ? `url("${picture}")` : undefined,
                      backgroundSize: "auto 100%",
                      backgroundRepeat: "repeat-x",
                      outline: index === current ? `2px solid ${COLORS.brand}` : undefined,
                      outlineOffset: -2,
                      touchAction: "none",
                    }}
                  >
                    <span
                      style={{
                        position: "absolute",
                        left: 4,
                        top: 4,
                        maxWidth: "calc(100% - 8px)",
                        overflow: "hidden",
                        whiteSpace: "nowrap",
                        textOverflow: "ellipsis",
                        padding: "1px 5px",
                        borderRadius: 4,
                        fontSize: 11,
                        color: "#fff",
                        background: "rgba(0, 0, 0, 0.55)",
                      }}
                    >
                      {label(index)}, {shown(lengths[index])}s
                    </span>
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
                          right: -6,
                          top: 0,
                          width: 12,
                          height: TRACK,
                          cursor: "ew-resize",
                          touchAction: "none",
                          zIndex: 1,
                          display: "flex",
                          justifyContent: "center",
                          alignItems: "center",
                        }}
                      >
                        <span
                          style={{
                            width: 4,
                            height: 24,
                            background: "#fff",
                            borderRadius: 2,
                            boxShadow: "0 0 0 1px #0004",
                          }}
                        />
                      </span>
                    </Tooltip>
                  )}
                </div>
              );
            })}
            {lanes.map((lane, row) =>
              laneSpans(lane.key, scenes, starts, lengths, musicName).map((span) => (
                <button
                  key={`${lane.key}-${span.index ?? "all"}-${span.start}`}
                  type="button"
                  data-testid={`lane-${lane.key}`}
                  title={span.label}
                  aria-label={`${lane.name}: ${span.label}`}
                  onClick={(event) =>
                    span.seek
                      ? onSeek(span.start)
                      : span.index !== null
                        ? onJump(span.index)
                        : onSeek(secondAt(event.clientX))
                  }
                  style={{
                    position: "absolute",
                    left: xOf(span.start) + 1,
                    top: lanesTop + row * (LANE + GAP),
                    width: Math.max(span.length * perSecond - 2, 4),
                    height: LANE,
                    padding: "0 6px",
                    border: span.tentative ? `1px dashed ${LANE_LOOK[lane.key].color}` : 0,
                    borderRadius: 4,
                    background: LANE_LOOK[lane.key].background,
                    color: LANE_LOOK[lane.key].color,
                    opacity: span.index !== null && span.index !== current ? 0.75 : 1,
                    fontSize: 11,
                    lineHeight: `${LANE - 2}px`,
                    textAlign: "left",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    cursor: "pointer",
                  }}
                >
                  {span.label}
                </button>
              )),
            )}
            {/* The playhead: a line over the ruler and every track, dragged by its handle or moved with the arrow keys. */}
            <div
              ref={head}
              role="slider"
              tabIndex={0}
              aria-label="Đầu phát"
              aria-valuemin={0}
              aria-valuemax={tenth(total)}
              aria-valuenow={0}
              data-testid="timeline-playhead"
              onPointerDown={startScrub}
              onKeyDown={(event) => {
                const by = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
                const to = event.key === "Home" ? 0 : event.key === "End" ? total : null;
                if (!by && to === null) return;
                event.preventDefault();
                event.stopPropagation();
                onSeek(to ?? Math.min(total, Math.max(0, position() + by * (event.shiftKey ? 1 : 0.5))));
              }}
              style={{
                position: "absolute",
                left: -7,
                top: 0,
                width: 14,
                height: height - 2,
                cursor: "ew-resize",
                touchAction: "none",
                zIndex: 2,
                transform: `translateX(${PAD}px)`,
                outline: "none",
              }}
            >
              <span
                style={{
                  position: "absolute",
                  left: 1,
                  top: 0,
                  width: 12,
                  height: 14,
                  borderRadius: "3px 3px 6px 6px",
                  background: COLORS.text,
                }}
              />
              <span style={{ position: "absolute", left: 6, top: 10, bottom: 0, width: 2, background: COLORS.text }} />
            </div>
          </div>
        </div>
      </Flex>
    </Flex>
  );
}

/** A track's name at the timeline's left, with its lock when the track has one. */
function TrackName({
  name,
  height,
  locked,
  onLock,
}: {
  name: string;
  height: number;
  locked?: boolean;
  onLock?: () => void;
}) {
  return (
    <Flex align="center" justify="space-between" gap={2} style={{ height, paddingLeft: 8, paddingRight: 2 }}>
      <Typography.Text style={{ fontSize: 12 }} type={locked ? "secondary" : undefined}>
        {name}
      </Typography.Text>
      {onLock && (
        <Tooltip title={locked ? `Mở khoá tầng ${name}` : `Khoá tầng ${name}: không kéo, sửa hay xoá được`}>
          <Button
            type="text"
            size="small"
            aria-label={locked ? `Mở khoá tầng ${name}` : `Khoá tầng ${name}`}
            aria-pressed={locked}
            icon={locked ? <LockOutlined /> : <UnlockOutlined />}
            onClick={onLock}
          />
        </Tooltip>
      )}
    </Flex>
  );
}
