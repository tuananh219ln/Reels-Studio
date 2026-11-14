"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, type VideoDetail } from "@/lib/api";
import type { PlatformKey } from "@/lib/postResults";

/** One platform of "Đăng lên N nền tảng": the request that starts its job. */
export type PostStep =
  | { platform: "facebook"; body: { fanpage_id: number; scheduled_at: string | null; auto_comment: boolean } }
  | { platform: "tiktok"; body: { account_id: number; mode: "draft"; privacy_level: null } };

/** How one platform's try ended: out (or scheduled), or why not and the job "Thử lại" sends again. */
export type PostOutcome = {
  platform: PlatformKey;
  ok: boolean;
  scheduled: boolean;
  error: string | null;
  retryJobId: number | null;
};

type Round = {
  steps: PostStep[];
  index: number;
  /** The job of the step being sent, while it runs. */
  jobId: number | null;
  sending: boolean;
  outcomes: PostOutcome[];
};

const PATHS: Record<PostStep["platform"], (videoId: number) => string> = {
  facebook: (videoId) => `/videos/${videoId}/publish`,
  tiktok: (videoId) => `/tiktok/videos/${videoId}/publish`,
};

/**
 * "Đăng lên N nền tảng": the api runs one job per video at a time, so the platforms go one after another, the next
 * sent once the job before it has ended (seen by the page's polling). `onDone` gets how each one ended. The round lives
 * in the open page: leaving it before the last platform is sent leaves that one unsent, as the rows then show.
 */
export function usePostRound(
  video: VideoDetail | null,
  receive: (video: VideoDetail) => void,
  onDone: (outcomes: PostOutcome[]) => void,
) {
  const round = useRef<Round | null>(null);
  const [running, setRunning] = useState(false);
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  }, [onDone]);

  const advance = useCallback(
    async (seen: VideoDetail) => {
      let current = seen;
      const now = round.current;
      if (!now || now.sending) return;
      if (now.jobId !== null) {
        if (current.active_job?.id === now.jobId) return;
        const failed = current.failed_job?.id === now.jobId ? current.failed_job : null;
        const step = now.steps[now.index];
        now.outcomes.push({
          platform: step.platform,
          ok: failed === null,
          scheduled: step.platform === "facebook" && step.body.scheduled_at !== null,
          error: failed?.error ?? null,
          retryJobId: failed?.id ?? null,
        });
        now.jobId = null;
        now.index += 1;
      }
      // Sends the next step; a step refused at once (or with no job to wait for) moves straight on to the one after.
      while (now.index < now.steps.length) {
        // Another job of the video (a teammate's) goes first; the step waits for it.
        if (current.active_job) return;
        const step = now.steps[now.index];
        now.sending = true;
        try {
          const next = await api<VideoDetail>(PATHS[step.platform](current.id), "POST", step.body);
          receive(next);
          current = next;
          now.jobId = next.active_job?.id ?? null;
          if (now.jobId !== null) return;
          now.outcomes.push({ platform: step.platform, ok: true, scheduled: false, error: null, retryJobId: null });
        } catch (err) {
          now.outcomes.push({
            platform: step.platform,
            ok: false,
            scheduled: false,
            error: errorMessage(err),
            retryJobId: null,
          });
        } finally {
          now.sending = false;
        }
        now.index += 1;
      }
      round.current = null;
      setRunning(false);
      done.current(now.outcomes);
    },
    [receive],
  );

  useEffect(() => {
    if (video) void advance(video);
  }, [video, advance]);

  const start = useCallback(
    (steps: PostStep[]) => {
      if (round.current || steps.length === 0 || !video) return;
      round.current = { steps, index: 0, jobId: null, sending: false, outcomes: [] };
      setRunning(true);
      void advance(video);
    },
    [video, advance],
  );

  return { start, running };
}
