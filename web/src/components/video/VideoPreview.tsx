"use client";

import {
  CaretRightOutlined,
  PauseOutlined,
  ReloadOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
} from "@ant-design/icons";
import { Alert, Button, Flex, Modal, Space, Switch, Typography } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import type { SceneData, VideoDetail } from "@/lib/api";
import { FRAME_HEIGHT, FRAME_WIDTH, SAFE, placeBox } from "./TextPositionModal";

// The renderer's timing and motion (reels_render.timeline, options, graph): keep these in step with it.
const XFADE_MS = 400;
const VOICE_LEAD_MS = 200;
const VOICE_TAIL_MS = 400;
const ZOOMS = { light: 1.06, medium: 1.12, strong: 1.18 } as const;
// Ducking drops the music to about a quarter while narration plays.
const DUCKED = 0.25;
const SPEECH_RATE = { slow: 0.85, normal: 1, fast: 1.15 } as const;
const SENTENCE_ENDS = [".", "!", "?", "…", ":"];
// A browser voice that never says it has finished must not hold the preview forever.
const SPEECH_GRACE_MS = 15_000;

const percent = (value: number, of: number) => `${(value / of) * 100}%`;
const seconds = (value: number) => value.toLocaleString("vi-VN", { maximumFractionDigits: 1 });

/** The narration a render would make for the scene (videos.spoken): its on-screen text, then its voice text. */
export function spokenText(video: VideoDetail, scene: SceneData): string {
  if (!video.voice_enabled || !scene.voice_text.trim()) {
    return "";
  }
  const screen = scene.text.replaceAll("*", "").replace(/\s+/g, " ").trim();
  if (!screen) {
    return scene.voice_text;
  }
  return `${screen}${SENTENCE_ENDS.some((end) => screen.endsWith(end)) ? "" : "."} ${scene.voice_text}`;
}

/** The browser's Vietnamese voice, preferring the natural-sounding online ones (Google, Microsoft). */
function vietnameseVoice(): SpeechSynthesisVoice | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    return null;
  }
  const voices = window.speechSynthesis.getVoices().filter((voice) => voice.lang.toLowerCase().startsWith("vi"));
  return voices.find((voice) => /google|microsoft|online|natural/i.test(voice.name)) ?? voices[0] ?? null;
}

type Phase = { index: number; prev: number | null; run: number };

/**
 * "Xem trước": the video played in the browser before any render, from the scenes' own frames, text boxes, clips,
 * music and narration, with the platforms' covered areas shown. Close to the MP4, not the MP4: FFmpeg's mix,
 * captions and the exact narration timing only come with a render.
 */
export default function VideoPreview({
  video,
  start,
  onClose,
}: {
  video: VideoDetail;
  start: number;
  onClose: () => void;
}) {
  const scenes = useMemo(
    () => [video.title_scene, ...video.scenes].filter((scene): scene is SceneData => scene !== null),
    [video.title_scene, video.scenes],
  );
  const [phase, setPhase] = useState<Phase>({ index: Math.min(start, scenes.length - 1), prev: null, run: 0 });
  const [playing, setPlaying] = useState(true);
  const [ended, setEnded] = useState(false);
  const [safeZone, setSafeZone] = useState(true);
  const [voice, setVoice] = useState<SpeechSynthesisVoice | null>(null);
  const [boxes, setBoxes] = useState<Record<string, { width: number; height: number }>>({});
  const stage = useRef<HTMLDivElement>(null);
  const music = useRef<HTMLAudioElement>(null);
  const narration = useRef<HTMLAudioElement>(null);
  // How long the current scene has played, across pauses, and which parts of it have finished.
  const clock = useRef({ run: 0, playedMs: 0 });
  const done = useRef({ run: 0, time: false, voice: false });

  const scene = scenes[phase.index];
  const text = scene ? spokenText(video, scene) : "";
  const label = (index: number) =>
    scenes[index]?.is_title ? "Cảnh tiêu đề" : `Cảnh ${index + (scenes[0]?.is_title ? 0 : 1)}`;
  const durationMs = (scene?.fitted_seconds ?? 0) * 1000;
  const missingVoice = video.voice_enabled && scenes.some((item) => spokenText(video, item) && !item.voice_url);

  // The browser lists its voices late (voiceschanged), so ask again when it does.
  useEffect(() => {
    if (!("speechSynthesis" in window)) {
      return;
    }
    const pick = () => setVoice(vietnameseVoice());
    const first = window.setTimeout(pick, 0);
    window.speechSynthesis.addEventListener("voiceschanged", pick);
    return () => {
      window.clearTimeout(first);
      window.speechSynthesis.removeEventListener("voiceschanged", pick);
      window.speechSynthesis.cancel();
    };
  }, []);

  /** Moves to a scene and plays it from its start; the scene before it stays underneath during the transition. */
  function goTo(index: number, keepPrev: boolean) {
    setEnded(false);
    setPlaying(true);
    setPhase((current) => {
      const next = { index, prev: keepPrev ? current.index : null, run: current.run + 1 };
      clock.current = { run: next.run, playedMs: 0 };
      return next;
    });
    if (music.current) {
      // The music runs from the video's start, so a preview from a later scene starts it that far in.
      const offset = scenes.slice(0, index).reduce((sum, item) => sum + item.fitted_seconds, 0);
      const length = music.current.duration;
      music.current.currentTime = Number.isFinite(length) && length > 0 ? offset % length : offset;
      void music.current.play().catch(() => undefined);
    }
  }

  /** Called when the scene's time is up and when its narration has finished: both move it on. */
  function finished(run: number, part: "time" | "voice") {
    if (done.current.run !== run) {
      return;
    }
    done.current[part] = true;
    if (!done.current.time || !done.current.voice) {
      return;
    }
    if (phase.index + 1 < scenes.length) {
      goTo(phase.index + 1, true);
    } else {
      setEnded(true);
      setPlaying(false);
      music.current?.pause();
    }
  }

  // The scene's clock: it runs while playing and keeps what has played across a pause.
  useEffect(() => {
    if (!playing || ended) {
      return;
    }
    const run = phase.run;
    const began = performance.now();
    const left = Math.max(0, durationMs - clock.current.playedMs);
    const timer = window.setTimeout(() => finished(run, "time"), left);
    return () => {
      window.clearTimeout(timer);
      if (clock.current.run === run) {
        clock.current.playedMs += performance.now() - began;
      }
    };
    // Restarted only by a new scene or by play/pause; `finished` reads the phase it was made with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase.run, playing, ended]);

  // The scene's narration: the MP3 a render already made, else the browser's free Vietnamese voice.
  useEffect(() => {
    const run = phase.run;
    const player = narration.current;
    done.current = { run, time: false, voice: false };
    const duck = (on: boolean) => {
      if (music.current && video.music) {
        music.current.volume = (video.music_volume / 100) * (on && video.options.ducking ? DUCKED : 1);
      }
    };
    duck(false);
    const timers: number[] = [];
    const voiceDone = () => {
      duck(false);
      timers.push(window.setTimeout(() => finished(run, "voice"), VOICE_TAIL_MS));
    };
    if (scene?.voice_url && player) {
      const audio = player;
      audio.src = scene.voice_url;
      audio.volume = Math.min(1, video.options.voice_volume);
      audio.onended = voiceDone;
      audio.onerror = voiceDone;
      timers.push(
        window.setTimeout(() => {
          duck(true);
          void audio.play().catch(voiceDone);
        }, VOICE_LEAD_MS),
      );
    } else if (text && voice) {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.voice = voice;
      utterance.lang = voice.lang;
      utterance.rate = SPEECH_RATE[video.options.voice_speed];
      utterance.volume = Math.min(1, video.options.voice_volume);
      utterance.onend = voiceDone;
      utterance.onerror = voiceDone;
      timers.push(
        window.setTimeout(() => {
          duck(true);
          window.speechSynthesis.cancel();
          window.speechSynthesis.speak(utterance);
        }, VOICE_LEAD_MS),
      );
      timers.push(window.setTimeout(voiceDone, durationMs + SPEECH_GRACE_MS));
    } else {
      timers.push(window.setTimeout(() => finished(run, "voice"), 0));
    }
    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
      player?.pause();
      if ("speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
    // A new scene, or a voice found late, starts the narration; pausing only pauses it (see `toggle`).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase.run, voice]);

  // The scene before the current one is shown only for the length of the transition.
  useEffect(() => {
    if (phase.prev === null) {
      return;
    }
    const run = phase.run;
    const timer = window.setTimeout(
      () => setPhase((current) => (current.run === run ? { ...current, prev: null } : current)),
      XFADE_MS,
    );
    return () => window.clearTimeout(timer);
  }, [phase.prev, phase.run]);

  // Music starts with the dialog (a click opened it, so the browser lets it play), as far in as the first scene.
  useEffect(() => {
    const audio = music.current;
    if (!audio || !video.music) {
      return;
    }
    audio.volume = video.music_volume / 100;
    const offset = scenes.slice(0, start).reduce((sum, item) => sum + item.fitted_seconds, 0);
    const begin = () => {
      audio.currentTime = audio.duration > 0 ? offset % audio.duration : 0;
      void audio.play().catch(() => undefined);
    };
    if (audio.readyState >= 1) {
      begin();
    } else {
      audio.addEventListener("loadedmetadata", begin, { once: true });
    }
    return () => {
      audio.removeEventListener("loadedmetadata", begin);
      audio.pause();
    };
    // Only when the dialog opens: later music changes from polling must not restart it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggle() {
    if (ended) {
      goTo(0, false);
      return;
    }
    const next = !playing;
    setPlaying(next);
    const media = [music.current, narration.current, ...(stage.current?.querySelectorAll("video") ?? [])];
    for (const element of media) {
      if (!element) {
        continue;
      }
      if (next) {
        // A finished narration is not started again.
        if (element !== narration.current || (element.currentTime > 0 && !element.ended)) {
          void element.play().catch(() => undefined);
        }
      } else {
        element.pause();
      }
    }
    if ("speechSynthesis" in window) {
      if (next) {
        window.speechSynthesis.resume();
      } else {
        window.speechSynthesis.pause();
      }
    }
  }

  return (
    <Modal
      open
      title="Xem trước video"
      onCancel={onClose}
      footer={null}
      width={520}
      destroyOnHidden
      styles={{ body: { paddingTop: 8 } }}
    >
      <Flex vertical gap={12} align="center">
        <div
          ref={stage}
          data-testid="preview-stage"
          style={{
            position: "relative",
            height: "min(68vh, 600px)",
            aspectRatio: `${FRAME_WIDTH} / ${FRAME_HEIGHT}`,
            overflow: "hidden",
            borderRadius: 8,
            background: "#000",
          }}
        >
          {phase.prev !== null && scenes[phase.prev] && (
            <SceneLayer
              key={`prev-${phase.run}`}
              video={video}
              scene={scenes[phase.prev]}
              playing={false}
              entering={false}
              atEnd
              boxes={boxes}
              onBox={(url, size) => setBoxes((current) => ({ ...current, [url]: size }))}
            />
          )}
          {scene && (
            <SceneLayer
              key={`scene-${phase.run}`}
              video={video}
              scene={scene}
              playing={playing && !ended}
              entering={phase.prev !== null}
              boxes={boxes}
              onBox={(url, size) => setBoxes((current) => ({ ...current, [url]: size }))}
            />
          )}
          {safeZone && <SafeZone />}
          <Typography.Text
            data-testid="preview-scene"
            style={{
              position: "absolute",
              right: 8,
              top: 8,
              padding: "1px 8px",
              borderRadius: 4,
              color: "#fff",
              background: "rgba(0,0,0,0.55)",
              fontSize: 12,
            }}
          >
            {label(phase.index)} · {seconds(scene?.fitted_seconds ?? 0)} giây
          </Typography.Text>
        </div>
        <Space wrap>
          <Button
            aria-label="Cảnh trước"
            icon={<StepBackwardOutlined />}
            disabled={phase.index === 0}
            onClick={() => goTo(phase.index - 1, false)}
          />
          <Button
            type="primary"
            icon={ended ? <ReloadOutlined /> : playing ? <PauseOutlined /> : <CaretRightOutlined />}
            onClick={toggle}
          >
            {ended ? "Xem lại" : playing ? "Tạm dừng" : "Tiếp tục"}
          </Button>
          <Button
            aria-label="Cảnh sau"
            icon={<StepForwardOutlined />}
            disabled={phase.index >= scenes.length - 1}
            onClick={() => goTo(phase.index + 1, false)}
          />
          <Button icon={<ReloadOutlined />} onClick={() => goTo(0, false)}>
            Từ đầu
          </Button>
        </Space>
        <Flex align="center" gap={8}>
          <Switch checked={safeZone} onChange={setSafeZone} aria-label="Vùng an toàn" size="small" />
          <Typography.Text>Hiện vùng bị che trên Reels / TikTok / Shorts</Typography.Text>
        </Flex>
        {missingVoice && !voice && (
          <Alert
            type="warning"
            showIcon
            data-testid="preview-no-voice"
            title="Trình duyệt này không có giọng tiếng Việt, nên cảnh chưa có giọng đọc sẽ im lặng. Dùng Chrome hoặc Edge để nghe thử."
          />
        )}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Bản xem trước gần đúng, chưa phải MP4: cảnh đã render có giọng ElevenLabs thật, cảnh chưa có dùng giọng tiếng
          Việt miễn phí của trình duyệt; phụ đề và cách trộn âm chỉ có khi render.
        </Typography.Text>
      </Flex>
      <audio ref={music} src={video.music?.url} loop preload="auto" />
      <audio ref={narration} preload="none" />
    </Modal>
  );
}

/** One scene on the stage: its frame (moving like the render's motion) or clip, and its text box on top. */
function SceneLayer({
  video,
  scene,
  playing,
  entering,
  atEnd = false,
  boxes,
  onBox,
}: {
  video: VideoDetail;
  scene: SceneData;
  playing: boolean;
  entering: boolean;
  atEnd?: boolean;
  boxes: Record<string, { width: number; height: number }>;
  onBox: (url: string, size: { width: number; height: number }) => void;
}) {
  const { transition, motion, zoom } = video.options;
  const end = ZOOMS[zoom];
  // The frame without text when there is one, so the box stays still while the picture moves; else the preview.
  const picture = scene.frame_url ?? scene.preview_url;
  const box = scene.frame_url ? scene.textbox_url : null;
  const size = box ? boxes[box] : undefined;
  const corner = size ? placeBox(size, scene.placed_at, scene.is_title) : null;
  const motionStyle = {
    "--z0": motion === "zoom_out" ? end : motion === "static" ? 1 : motion === "pan" ? end : 1,
    "--z1": motion === "zoom_in" ? end : motion === "pan" ? end : 1,
    "--x0": motion === "pan" ? `${(end - 1) * 50}%` : "0%",
    "--x1": motion === "pan" ? `${-(end - 1) * 50}%` : "0%",
    animationName: "preview-motion",
    animationDuration: `${scene.fitted_seconds}s`,
    animationTimingFunction: "linear",
    animationFillMode: "both",
    // The scene going out holds its last frame while the next one comes in.
    animationDelay: atEnd ? `-${scene.fitted_seconds}s` : "0s",
    animationPlayState: playing && !atEnd ? "running" : "paused",
  } as React.CSSProperties;
  const enter =
    entering && transition !== "cut"
      ? {
          animationName: `preview-${transition}`,
          animationDuration: `${XFADE_MS}ms`,
          animationTimingFunction: "ease-out",
          animationFillMode: "both",
        }
      : undefined;

  return (
    <div style={{ position: "absolute", inset: 0, ...enter }}>
      {scene.video ? (
        <video
          src={scene.video.url}
          muted
          playsInline
          autoPlay={playing}
          preload="auto"
          onLoadedMetadata={(event) => {
            event.currentTarget.currentTime = scene.video?.start ?? 0;
          }}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : picture ? (
        // eslint-disable-next-line @next/next/no-img-element -- frames are drawn by the api; next/image adds nothing
        <img
          src={picture}
          alt=""
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", ...motionStyle }}
        />
      ) : (
        <Flex align="center" justify="center" style={{ position: "absolute", inset: 0, background: "#262626" }}>
          <Typography.Text style={{ color: "#bfbfbf" }}>Chưa có ảnh</Typography.Text>
        </Flex>
      )}
      {box && (
        // The exact box image the render draws, placed where the render puts it.
        // eslint-disable-next-line @next/next/no-img-element -- drawn by the api with the renderer's own code
        <img
          src={box}
          alt=""
          onLoad={(event) =>
            onBox(box, { width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })
          }
          style={{
            position: "absolute",
            visibility: corner ? "visible" : "hidden",
            left: corner ? percent(corner[0], FRAME_WIDTH) : 0,
            top: corner ? percent(corner[1], FRAME_HEIGHT) : 0,
            width: size ? percent(size.width, FRAME_WIDTH) : undefined,
          }}
        />
      )}
    </div>
  );
}

/** The parts of the frame the apps cover (top bar, right button column, caption and name at the bottom), shaded. */
function SafeZone() {
  const shade = "rgba(255, 77, 79, 0.28)";
  const area = (style: React.CSSProperties, name: string) => (
    <div style={{ position: "absolute", background: shade, ...style }}>
      <span
        style={{ position: "absolute", left: 6, top: 4, color: "#fff", fontSize: 10, textShadow: "0 1px 2px #000" }}
      >
        {name}
      </span>
    </div>
  );
  return (
    <div data-testid="preview-safe-zone" style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      {area({ left: 0, right: 0, top: 0, height: percent(SAFE.top, FRAME_HEIGHT) }, "Thanh trên của app")}
      {area({ left: 0, right: 0, top: percent(SAFE.bottom, FRAME_HEIGHT), bottom: 0 }, "Tên kênh, caption, nhạc")}
      {area(
        {
          left: percent(SAFE.right, FRAME_WIDTH),
          right: 0,
          top: percent(SAFE.top, FRAME_HEIGHT),
          height: percent(SAFE.bottom - SAFE.top, FRAME_HEIGHT),
        },
        "Nút",
      )}
      <div
        style={{
          position: "absolute",
          left: percent(SAFE.left, FRAME_WIDTH),
          top: percent(SAFE.top, FRAME_HEIGHT),
          width: percent(SAFE.right - SAFE.left, FRAME_WIDTH),
          height: percent(SAFE.bottom - SAFE.top, FRAME_HEIGHT),
          border: "1px dashed rgba(255,255,255,0.8)",
        }}
      />
    </div>
  );
}
