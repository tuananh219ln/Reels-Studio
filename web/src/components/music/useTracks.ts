"use client";

import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, type MusicOptions, type MusicTrack } from "@/lib/api";

export type TrackFilters = { topic?: string; mood?: string; q: string };

/** The library filtered on the server; typing in the search waits a moment before asking again. */
export function useTracks(filters: TrackFilters, enabled = true) {
  const { message } = App.useApp();
  const [tracks, setTracks] = useState<MusicTrack[]>([]);
  const [loading, setLoading] = useState(true);
  const { topic, mood, q } = filters;

  const reload = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams();
    const values: [string, string | undefined][] = [["topic", topic], ["mood", mood], ["q", q.trim()]];
    for (const [name, value] of values) {
      if (value) {
        params.set(name, value);
      }
    }
    try {
      setTracks(await api<MusicTrack[]>(`/music?${params}`));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [message, topic, mood, q]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const timer = setTimeout(reload, 250);
    return () => clearTimeout(timer);
  }, [enabled, reload]);

  return { tracks, loading, reload };
}

/** The fixed topic and mood lists, loaded once per component. */
export function useMusicOptions(): MusicOptions {
  const [options, setOptions] = useState<MusicOptions>({ topics: [], moods: [] });

  useEffect(() => {
    // Without the lists the selects stay empty and the api still refuses unknown values.
    api<MusicOptions>("/music/options").then(setOptions, () => undefined);
  }, []);

  return options;
}
