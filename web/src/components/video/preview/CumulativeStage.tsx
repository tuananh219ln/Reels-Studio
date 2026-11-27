"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

const FRAME_WIDTH = 1080;
const FRAME_HEIGHT = 1920;
const percent = (value: number, of: number) => `${(value / of) * 100}%`;

type Step = { start: number; end: number; url: string; left: number; top: number; width: number; height: number };

/**
 * PC Shopee's "Cộng dồn" captions on the phone: the phrase so far, each step the exact picture the render lays on, shown
 * for its own seconds of the scene (the words come in as the narration is said, the estimate until the narration is
 * made). It follows the preview's clock every frame, like the layers, without rendering again.
 */
export default function CumulativeStage({
  url,
  elapsed,
}: {
  /** `/api/scenes/<id>/cumulative?v=...`, the scene's `cumulative_url`. */
  url: string;
  /** Seconds into the scene, read every frame. */
  elapsed: () => number;
}) {
  const [steps, setSteps] = useState<Step[]>([]);
  const [shown, setShown] = useState(-1);
  const current = useRef({ steps, elapsed });
  useEffect(() => {
    current.current = { steps, elapsed };
  });

  useEffect(() => {
    let cancelled = false;
    api<{ steps: Step[] }>(url.replace(/^\/api/, ""))
      .then((data) => !cancelled && setSteps(data.steps))
      .catch(() => !cancelled && setSteps([]));
    return () => {
      cancelled = true;
    };
  }, [url]);

  useEffect(() => {
    let frame = 0;
    const tick = () => {
      const { steps: list, elapsed: seconds } = current.current;
      const now = seconds();
      const index = list.findIndex((step) => now >= step.start && now < step.end);
      setShown((before) => (before === index ? before : index));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  const step = steps[shown];
  if (!step) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element -- the render's own picture, not a page image
    <img
      data-testid="cumulative-step"
      alt=""
      src={step.url}
      draggable={false}
      style={{
        position: "absolute",
        left: percent(step.left, FRAME_WIDTH),
        top: percent(step.top, FRAME_HEIGHT),
        width: percent(step.width, FRAME_WIDTH),
        height: percent(step.height, FRAME_HEIGHT),
        pointerEvents: "none",
        zIndex: 2,
      }}
    />
  );
}
