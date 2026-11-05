"use client";

import { useEffect, useRef, useState } from "react";
import type { SceneLayer } from "@/lib/api";
import { ENTRANCE_SECONDS, FRAME_HEIGHT, FRAME_WIDTH, layerCorner } from "./layers";

// The render core's slide-up distance (layers.SLIDE_UP_PX), in frame pixels.
const SLIDE_UP = 120;
const percent = (value: number, of: number) => `${(value / of) * 100}%`;

/**
 * The scene's layers on the phone, each the exact picture the render lays on, shown for its own seconds and coming
 * in as the render's overlay does (fading over 0.3 s, a slide moving it the same way). It follows the preview's
 * clock every frame without rendering again. While the preview stands still a layer can be picked (outlined) and
 * dragged to a new place.
 */
export default function LayerStage({
  layers,
  elapsed,
  stage,
  selected,
  editable,
  onSelect,
  onMove,
}: {
  layers: SceneLayer[];
  /** Seconds into the scene, read every frame. */
  elapsed: () => number;
  stage: React.RefObject<HTMLDivElement | null>;
  selected: number | null;
  /** Layers can be picked and dragged (paused, edit mode, the layers' track not locked). */
  editable: boolean;
  onSelect: (id: number) => void;
  onMove: (layer: SceneLayer, x: number, y: number) => void;
}) {
  const [sizes, setSizes] = useState<Record<string, { width: number; height: number }>>({});
  const [dragged, setDragged] = useState<{ id: number; x: number; y: number } | null>(null);
  const elements = useRef(new Map<number, HTMLImageElement>());
  const current = useRef({ layers, elapsed, sizes, dragged });
  useEffect(() => {
    current.current = { layers, elapsed, sizes, dragged };
  });

  useEffect(() => {
    let frame = 0;
    const tick = () => {
      const { layers: list, elapsed: at, sizes: known, dragged: moving } = current.current;
      const now = at();
      for (const layer of list) {
        const element = elements.current.get(layer.id);
        const size = known[layer.image_url];
        if (!element || !size) continue;
        const shown = (now >= layer.start && now < layer.start + layer.seconds) || moving?.id === layer.id;
        const progress =
          layer.animation === "none" || moving ? 1 : Math.min(1, Math.max(0, (now - layer.start) / ENTRANCE_SECONDS));
        const [left] = layerCorner(size.width, size.height, layer);
        const dx = layer.animation === "slide_left" ? -(left + size.width) * (1 - progress) : 0;
        const dy = layer.animation === "slide_up" ? SLIDE_UP * (1 - progress) : 0;
        element.style.visibility = shown ? "visible" : "hidden";
        element.style.opacity = String(progress);
        // In the stage's own width (cqw), so it moves as far as in the 1080-pixel frame.
        element.style.transform = `translate(${(dx / FRAME_WIDTH) * 100}cqw, ${(dy / FRAME_WIDTH) * 100}cqw)`;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  /** The pointer's place in frame pixels. */
  function framePoint(event: PointerEvent | React.PointerEvent): [number, number] | null {
    const rect = stage.current?.getBoundingClientRect();
    if (!rect) return null;
    return [
      Math.round(((event.clientX - rect.left) / rect.width) * FRAME_WIDTH),
      Math.round(((event.clientY - rect.top) / rect.height) * FRAME_HEIGHT),
    ];
  }

  function startDrag(event: React.PointerEvent, layer: SceneLayer) {
    event.stopPropagation();
    onSelect(layer.id);
    if (!editable) return;
    event.preventDefault();
    const from = framePoint(event);
    if (!from) return;
    let last: [number, number] | null = null;
    const move = (moveEvent: PointerEvent) => {
      const point = framePoint(moveEvent);
      if (!point) return;
      const x = Math.min(FRAME_WIDTH, Math.max(0, layer.x + point[0] - from[0]));
      const y = Math.min(FRAME_HEIGHT, Math.max(0, layer.y + point[1] - from[1]));
      last = [x, y];
      setDragged({ id: layer.id, x, y });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      if (last && (last[0] !== layer.x || last[1] !== layer.y)) onMove(layer, last[0], last[1]);
      setDragged(null);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  return (
    <>
      {layers.map((layer) => {
        const size = sizes[layer.image_url];
        const place = dragged?.id === layer.id ? { x: dragged.x, y: dragged.y } : layer;
        const corner = size ? layerCorner(size.width, size.height, place) : null;
        return (
          // eslint-disable-next-line @next/next/no-img-element -- drawn by the api with the render core's own code
          <img
            key={layer.id}
            ref={(element) => {
              if (element) elements.current.set(layer.id, element);
              else elements.current.delete(layer.id);
            }}
            src={layer.image_url}
            alt=""
            draggable={false}
            data-testid="preview-layer"
            data-layer={layer.id}
            onLoad={(event) => {
              const { naturalWidth: width, naturalHeight: height } = event.currentTarget;
              setSizes((known) => ({ ...known, [layer.image_url]: { width, height } }));
            }}
            onPointerDown={(event) => startDrag(event, layer)}
            style={{
              position: "absolute",
              zIndex: 2,
              visibility: "hidden",
              left: corner ? percent(corner[0], FRAME_WIDTH) : 0,
              top: corner ? percent(corner[1], FRAME_HEIGHT) : 0,
              width: size ? percent(size.width, FRAME_WIDTH) : undefined,
              cursor: editable ? "grab" : "pointer",
              touchAction: editable ? "none" : undefined,
              outline: selected === layer.id ? "2px dashed #ff4fd8" : undefined,
              outlineOffset: 3,
            }}
          />
        );
      })}
    </>
  );
}
