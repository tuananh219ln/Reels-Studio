"use client";

import {
  CaretRightOutlined,
  PauseOutlined,
  ReloadOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
} from "@ant-design/icons";
import { Alert, Button, Drawer, Flex, Popconfirm, Segmented, Select, Space, Switch, Typography } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { COLORS } from "@/app/theme";
import type { SceneData, VideoDetail } from "@/lib/api";
import { Phone } from "./phone/Phone";
import PlatformFrame, { PLATFORM_LABELS, type Platform } from "./PlatformFrame";
import { FRAME_HEIGHT, FRAME_WIDTH, SAFE, placeBox } from "./TextPositionModal";

const PLATFORM_KEY = "reels-studio.preview-platform";
const VOICE_KEY = "reels-studio.preview-voice";

// The renderer's timing and motion (reels_render.timeline, options, graph): keep these in step with it.
const XFADE_MS = 400;
const VOICE_LEAD_MS = 200;
const VOICE_TAIL_MS = 400;
const ZOOMS = { light: 1.06, medium: 1.12, strong: 1.18 } as const;
// Ducking drops the music to about a quarter while narration plays.
const DUCKED = 0.25;
// A browser voice that never says it has finished must not hold the preview forever.
const SPEECH_GRACE_MS = 15_000;

// The phone's outer size over its screen (Stageshow's iPhone: a 402 × 874 pt screen, a 13 pt band each side).
const PHONE_RATIO = (402 + 26) / (874 + 26);

/** The phone's width: as tall as fits the drawer's height, never wider than a small screen. */
function phoneWidth(): number {
  const height = Math.min(window.innerHeight * 0.74, 760);
  return Math.round(Math.min(height * PHONE_RATIO, window.innerWidth - 48));
}

/** The status bar shows the time in Vietnam, like everywhere else in the app. */
const clockNow = () =>
  new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Ho_Chi_Minh" }).format(
    new Date(),
  );

const percent = (value: number, of: number) => `${(value / of) * 100}%`;
const seconds = (value: number) => value.toLocaleString("vi-VN", { maximumFractionDigits: 1 });

// Edge's neural voices (HoaiMy, NamMinh) sound far more natural than Chrome's Google voice.
const NATURAL = /natural|online/i;

/** How natural a browser voice sounds: Microsoft's neural ones first, then Google's, then the system's own. */
function rank(voice: SpeechSynthesisVoice): number {
  return NATURAL.test(voice.name) ? 0 : /google/i.test(voice.name) ? 1 : 2;
}

/** The browser's Vietnamese voices, the most natural-sounding first. */
function vietnameseVoices(): SpeechSynthesisVoice[] {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    return [];
  }
  return window.speechSynthesis
    .getVoices()
    .filter((voice) => voice.lang.toLowerCase().startsWith("vi"))
    .sort((a, b) => rank(a) - rank(b));
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
  onMakeVoices,
}: {
  video: VideoDetail;
  start: number;
  onClose: () => void;
  /** "Tạo giọng thật": queues the job that has ElevenLabs read the scenes still without its narration. */
  onMakeVoices: () => void;
}) {
  const scenes = useMemo(
    () => [video.title_scene, ...video.scenes].filter((scene): scene is SceneData => scene !== null),
    [video.title_scene, video.scenes],
  );
  const [phase, setPhase] = useState<Phase>({ index: Math.min(start, scenes.length - 1), prev: null, run: 0 });
  const [playing, setPlaying] = useState(true);
  const [ended, setEnded] = useState(false);
  // The app frame drawn over the video, Reels by default; each member's choice is remembered in their browser.
  const [platform, setPlatform] = useState<Platform | "none">(() => {
    try {
      const saved = window.localStorage.getItem(PLATFORM_KEY);
      return saved && ["reels", "tiktok", "shorts", "none"].includes(saved) ? (saved as Platform | "none") : "reels";
    } catch {
      return "reels";
    }
  });
  const [guide, setGuide] = useState(false);
  const [width, setWidth] = useState(phoneWidth);
  const [statusTime] = useState(clockNow);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  // The browser voice each member picked, remembered in their browser; the most natural one otherwise.
  const [voiceName, setVoiceName] = useState<string | null>(() => {
    try {
      return window.localStorage.getItem(VOICE_KEY);
    } catch {
      return null;
    }
  });
  const voice = voices.find((item) => item.voiceURI === voiceName) ?? voices[0] ?? null;
  const [boxes, setBoxes] = useState<Record<string, { width: number; height: number }>>({});
  const stage = useRef<HTMLDivElement>(null);
  const music = useRef<HTMLAudioElement>(null);
  const narration = useRef<HTMLAudioElement>(null);
  // How long the current scene has played, across pauses, and which parts of it have finished.
  const clock = useRef({ run: 0, playedMs: 0 });
  const done = useRef({ run: 0, time: false, voice: false });

  const scene = scenes[phase.index];
  const text = scene?.spoken_text ?? "";
  const label = (index: number) =>
    scenes[index]?.is_title ? "Cảnh tiêu đề" : `Cảnh ${index + (scenes[0]?.is_title ? 0 : 1)}`;
  const durationMs = (scene?.fitted_seconds ?? 0) * 1000;
  const unvoiced = scenes.filter((item) => item.spoken_text && !item.voice_url).length;
  const missingVoice = unvoiced > 0;
  const voicing = video.active_job?.kind === "voice";

  useEffect(() => {
    const resize = () => setWidth(phoneWidth());
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  // The browser lists its voices late (voiceschanged), so ask again when it does.
  useEffect(() => {
    if (!("speechSynthesis" in window)) {
      return;
    }
    const pick = () => setVoices(vietnameseVoices());
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
      utterance.rate = video.options.voice_speed;
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
    // A new scene, or a voice found late or picked, starts the narration; pausing only pauses it (see `toggle`).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase.run, voice?.voiceURI]);

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

  function choosePlatform(next: Platform | "none") {
    setPlatform(next);
    try {
      window.localStorage.setItem(PLATFORM_KEY, next);
    } catch {
      // A browser that refuses storage just forgets the choice.
    }
  }

  function chooseVoice(next: string) {
    setVoiceName(next);
    try {
      window.localStorage.setItem(VOICE_KEY, next);
    } catch {
      // A browser that refuses storage just forgets the choice.
    }
  }

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

  const channel = video.publication?.fanpage ?? video.fanpages[0]?.name ?? "Tên kênh";
  const caption = [video.caption.split("\n")[0], ...video.hashtags].filter(Boolean).join(" ");
  const sound = video.music?.name ?? "Âm thanh gốc";
  const total = scenes.reduce((sum, item) => sum + item.fitted_seconds, 0);

  return (
    // A drawer from the right, so the page it previews stays in sight beside it.
    <Drawer
      open
      placement="right"
      title="Xem trước video"
      aria-label="Xem trước video"
      onClose={onClose}
      size="min(820px, 100vw)"
      destroyOnHidden
      styles={{ body: { paddingTop: 8 } }}
    >
      <Flex wrap gap={24} justify="center">
        <Flex vertical gap={10} align="center">
          {/* A real phone's geometry around the frame: the 9:16 video sits under the status bar, as the apps show it. */}
          <Phone width={width} frame="pro" dark wallpaper="#000" time={statusTime}>
            <div
              ref={stage}
              data-testid="preview-stage"
              style={{
                position: "relative",
                width: "100%",
                aspectRatio: `${FRAME_WIDTH} / ${FRAME_HEIGHT}`,
                overflow: "hidden",
                background: "#000",
                containerType: "inline-size",
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
              {platform !== "none" && (
                <PlatformFrame platform={platform} channel={channel} caption={caption} music={sound} />
              )}
              {guide && <SafeZone />}
            </div>
          </Phone>
          {/* One segment per scene, as long as the scene; the current one fills as it plays. Click to jump. */}
          <Flex gap={3} style={{ width: "100%" }} data-testid="preview-timeline">
            {scenes.map((item, index) => (
              <button
                key={item.id}
                type="button"
                aria-label={`Xem ${label(index)}`}
                onClick={() => goTo(index, false)}
                style={{
                  flex: item.fitted_seconds,
                  height: 6,
                  padding: 0,
                  border: 0,
                  borderRadius: 3,
                  cursor: "pointer",
                  overflow: "hidden",
                  background: index < phase.index ? COLORS.primary : COLORS.border,
                }}
              >
                {index === phase.index && (
                  <span
                    key={phase.run}
                    style={{
                      display: "block",
                      height: "100%",
                      background: COLORS.primary,
                      animationName: "preview-progress",
                      animationDuration: `${item.fitted_seconds}s`,
                      animationTimingFunction: "linear",
                      animationFillMode: "both",
                      animationPlayState: playing && !ended ? "running" : "paused",
                    }}
                  />
                )}
              </button>
            ))}
          </Flex>
          <Flex justify="space-between" style={{ width: "100%" }}>
            <Typography.Text strong data-testid="preview-scene">
              {label(phase.index)} · {seconds(scene?.fitted_seconds ?? 0)} giây
            </Typography.Text>
            <Typography.Text type="secondary">
              {phase.index + 1}/{scenes.length} cảnh · {seconds(total)} giây
            </Typography.Text>
          </Flex>
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
              style={{ minWidth: 120 }}
            >
              {ended ? "Xem lại" : playing ? "Tạm dừng" : "Tiếp tục"}
            </Button>
            <Button
              aria-label="Cảnh sau"
              icon={<StepForwardOutlined />}
              disabled={phase.index >= scenes.length - 1}
              onClick={() => goTo(phase.index + 1, false)}
            />
            <Button aria-label="Từ đầu" icon={<ReloadOutlined />} onClick={() => goTo(0, false)} />
          </Space>
        </Flex>

        <Flex vertical gap={16} style={{ flex: "1 1 260px", minWidth: 0, maxWidth: 360 }}>
          <div>
            <Typography.Text strong style={{ display: "block", marginBottom: 6 }}>
              Khung ứng dụng
            </Typography.Text>
            <Segmented
              block
              aria-label="Khung ứng dụng"
              value={platform}
              onChange={(value) => choosePlatform(value as Platform | "none")}
              options={[
                ...(Object.keys(PLATFORM_LABELS) as Platform[]).map((key) => ({
                  value: key,
                  label: PLATFORM_LABELS[key],
                })),
                { value: "none", label: "Không" },
              ]}
            />
            <Typography.Text type="secondary" style={{ display: "block", fontSize: 12, marginTop: 6 }}>
              Giao diện mô phỏng của app trên điện thoại: chữ và hình bị che chỗ nào thì sẽ bị che như vậy khi đăng.
            </Typography.Text>
          </div>
          <Flex align="center" gap={8}>
            <Switch checked={guide} onChange={setGuide} aria-label="Vùng an toàn" size="small" />
            <Typography.Text>Đường vùng an toàn của mẫu</Typography.Text>
          </Flex>
          <div>
            <Typography.Text strong style={{ display: "block", marginBottom: 6 }}>
              Các cảnh
            </Typography.Text>
            <Flex vertical gap={4} style={{ maxHeight: 260, overflowY: "auto" }}>
              {scenes.map((item, index) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => goTo(index, false)}
                  style={{
                    display: "flex",
                    gap: 8,
                    alignItems: "center",
                    padding: "6px 8px",
                    border: `1px solid ${index === phase.index ? COLORS.primary : COLORS.border}`,
                    borderRadius: 6,
                    background: index === phase.index ? COLORS.primaryBg : COLORS.surface,
                    cursor: "pointer",
                    textAlign: "left",
                  }}
                >
                  <Typography.Text strong style={{ flex: "none", fontSize: 13 }}>
                    {label(index)}
                  </Typography.Text>
                  <Typography.Text type="secondary" ellipsis style={{ flex: 1, minWidth: 0, fontSize: 12 }}>
                    {item.text.replaceAll("*", "").replace(/\s+/g, " ").trim() || "(không có chữ)"}
                  </Typography.Text>
                  <Typography.Text type="secondary" style={{ flex: "none", fontSize: 12 }}>
                    {seconds(item.fitted_seconds)}s
                  </Typography.Text>
                </button>
              ))}
            </Flex>
          </div>
          {(missingVoice || voicing) && (
            <Flex vertical gap={8} data-testid="preview-voice">
              <Typography.Text strong>Giọng đọc</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {voicing
                  ? "ElevenLabs đang đọc các cảnh, xong sẽ tự dùng giọng thật."
                  : `${unvoiced} cảnh chưa có giọng ElevenLabs nên đang đọc bằng giọng miễn phí của trình duyệt.`}
              </Typography.Text>
              {voices.length > 0 ? (
                <Select
                  aria-label="Giọng trình duyệt"
                  value={voice?.voiceURI}
                  onChange={chooseVoice}
                  options={voices.map((item) => ({ value: item.voiceURI, label: item.name }))}
                />
              ) : (
                <Alert
                  type="warning"
                  showIcon
                  data-testid="preview-no-voice"
                  title="Trình duyệt này không có giọng tiếng Việt, nên cảnh chưa có giọng đọc sẽ im lặng. Dùng Edge hoặc Chrome để nghe thử."
                />
              )}
              {voices.length > 0 && !voices.some((item) => NATURAL.test(item.name)) && (
                <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="preview-edge-tip">
                  Giọng tự nhiên hơn: mở trang này bằng Microsoft Edge để có giọng HoaiMy, NamMinh.
                </Typography.Text>
              )}
              <Popconfirm
                title="Tạo giọng thật bằng ElevenLabs?"
                description={`ElevenLabs đọc ${unvoiced} cảnh, tốn credit một lần. Render sau đó dùng lại, không tốn thêm.`}
                okText="Tạo giọng"
                cancelText="Thôi"
                onConfirm={onMakeVoices}
                disabled={voicing || Boolean(video.active_job)}
              >
                <Button block loading={voicing} disabled={!voicing && Boolean(video.active_job)}>
                  Tạo giọng thật (ElevenLabs)
                </Button>
              </Popconfirm>
            </Flex>
          )}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Bản xem trước gần đúng, chưa phải MP4. Cảnh đã có giọng ElevenLabs (sau một lần render hoặc “Tạo giọng
            thật”) dùng giọng đó, cảnh khác dùng giọng tiếng Việt miễn phí của trình duyệt. Phụ đề và cách trộn âm chỉ
            có khi render.
          </Typography.Text>
        </Flex>
      </Flex>
      <audio ref={music} src={video.music?.url} loop preload="auto" />
      <audio ref={narration} preload="none" />
    </Drawer>
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
            event.currentTarget.playbackRate = scene.video?.speed ?? 1;
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

/** The template's safe zone (reels_render.textbox), dashed: the text box always stays inside it. */
function SafeZone() {
  return (
    <div
      data-testid="preview-safe-zone"
      style={{
        position: "absolute",
        left: percent(SAFE.left, FRAME_WIDTH),
        top: percent(SAFE.top, FRAME_HEIGHT),
        width: percent(SAFE.right - SAFE.left, FRAME_WIDTH),
        height: percent(SAFE.bottom - SAFE.top, FRAME_HEIGHT),
        border: "1.5px dashed #ffd60a",
        pointerEvents: "none",
      }}
    />
  );
}
