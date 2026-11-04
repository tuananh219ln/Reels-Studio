"use client";

import { useState } from "react";
import type { VideoDetail } from "@/lib/api";

/** One change made in the preview, with the call that puts it back and the one that makes it again. */
export type Step = { label: string; undo: () => Promise<VideoDetail>; redo: () => Promise<VideoDetail> };

const LIMIT = 50;

/**
 * "Hoàn tác" / "Làm lại" for what the preview changes on the phone (text, its place, seconds, the clip's part, the
 * transition, the order). Each step saves through the api like the change did, so a teammate sees it too; a new
 * change drops what could be done again.
 */
export function useHistory(save: (call: () => Promise<VideoDetail>) => Promise<boolean>) {
  const [stacks, setStacks] = useState<{ past: Step[]; future: Step[] }>({ past: [], future: [] });

  /** Makes a change and keeps it for "Hoàn tác" once the api took it. */
  async function run(step: Step) {
    if (await save(step.redo)) {
      setStacks((current) => ({ past: [...current.past.slice(-(LIMIT - 1)), step], future: [] }));
    }
  }

  async function undo() {
    const step = stacks.past.at(-1);
    if (step && (await save(step.undo))) {
      setStacks((current) => ({ past: current.past.slice(0, -1), future: [...current.future, step] }));
    }
  }

  async function redo() {
    const step = stacks.future.at(-1);
    if (step && (await save(step.redo))) {
      setStacks((current) => ({ past: [...current.past, step], future: current.future.slice(0, -1) }));
    }
  }

  return {
    run,
    undo,
    redo,
    canUndo: stacks.past.length > 0,
    canRedo: stacks.future.length > 0,
    undoLabel: stacks.past.at(-1)?.label ?? null,
    redoLabel: stacks.future.at(-1)?.label ?? null,
  };
}
