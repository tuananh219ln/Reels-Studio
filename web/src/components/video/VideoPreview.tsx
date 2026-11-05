"use client";

import {
  CaretRightOutlined,
  PauseOutlined,
  ReloadOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Collapse,
  Drawer,
  Flex,
  InputNumber,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Switch,
  Typography,
} from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import ListenVolume, { useListen } from "@/components/ListenVolume";
import { COLORS } from "@/app/theme";
import { api, errorMessage, upload, type SceneData, type VideoDetail, type VideoOptions } from "@/lib/api";
import ClipTrim from "./preview/ClipTrim";
import { coveredBy } from "./preview/coverage";
import { useHistory } from "./preview/history";
import PreviewTimeline from "./preview/PreviewTimeline";
import PreviewToolbar from "./preview/PreviewToolbar";
import { useEditor } from "./AutoSaveField";
import { VoicePicker } from "./VideoSettings";
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
/** Frame pixels within which a dragged box snaps to the frame's middle. */
const SNAP = 24;

/** A guide line across the stage at the frame's middle, shown while a box snaps to it. */
function guideStyle(axis: "x" | "y"): React.CSSProperties {
  return axis === "x"
    ? { position: "absolute", top: 0, bottom: 0, left: "50%", width: 1, background: "#ff4fd8", zIndex: 2 }
    : { position: "absolute", left: 0, right: 0, top: "50%", height: 1, background: "#ff4fd8", zIndex: 2 };
}
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
  // Editing from the preview: what the editor allows, the text box being dragged, and where a drop applies.
  const editor = useEditor();
  const { message } = App.useApp();
  const editable = !editor.locked && !editor.readOnly;
  const [dragged, setDragged] = useState<{ sceneId: number; centre: [number, number] } | null>(null);
  const [scope, setScope] = useState<"scene" | "all">("scene");
  // The clip frame the trim bar asks the phone to show while its window is dragged.
  const [seek, setSeek] = useState<number | null>(null);
  // "Sửa chữ tại chỗ": the scene whose on-screen text is being typed over its box, and the text so far.
  const [typing, setTyping] = useState<{ sceneId: number; value: string } | null>(null);
  const swipe = useRef<{ x: number; y: number; at: number } | null>(null);
  const stage = useRef<HTMLDivElement>(null);
  const music = useRef<HTMLAudioElement>(null);
  const narration = useRef<HTMLAudioElement>(null);
  // How long the current scene has played, across pauses, and which parts of it have finished.
  const clock = useRef({ run: 0, playedMs: 0 });
  const done = useRef({ run: 0, time: false, voice: false });
  // The listener's own level multiplies the video's mix, and the narration lowers the music while it plays.
  const { factor: listen } = useListen();
  const listenRef = useRef(listen);
  const ducked = useRef(false);

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

  function musicLevel(duckedNow: boolean, factor: number) {
    return (video.music_volume / 100) * (duckedNow && video.options.ducking ? DUCKED : 1) * factor;
  }

  // A new listening level applies at once to what is playing; the browser's voice takes it from its next scene.
  useEffect(() => {
    listenRef.current = listen;
    if (music.current && video.music) {
      music.current.volume = musicLevel(ducked.current, listen);
    }
    if (narration.current) {
      narration.current.volume = Math.min(1, video.options.voice_volume) * listen;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only the listener's level changes the players here
  }, [listen]);

  // The scene's narration: the MP3 a render already made, else the browser's free Vietnamese voice.
  useEffect(() => {
    const run = phase.run;
    const player = narration.current;
    done.current = { run, time: false, voice: false };
    const duck = (on: boolean) => {
      ducked.current = on;
      if (music.current && video.music) {
        music.current.volume = musicLevel(on, listenRef.current);
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
      audio.volume = Math.min(1, video.options.voice_volume) * listenRef.current;
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
      utterance.volume = Math.min(1, video.options.voice_volume) * listenRef.current;
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
    audio.volume = musicLevel(false, listenRef.current);
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

  /** Saves a change made in the preview, as the scene cards do; the drawer then shows the saved video. */
  async function save(call: () => Promise<VideoDetail>): Promise<boolean> {
    try {
      editor.onSaved(await call());
      return true;
    } catch (err) {
      message.error(errorMessage(err));
      return false;
    }
  }
  const history = useHistory(save);
  const patchOf = (id: number, body: object) => () => api<VideoDetail>(`/scenes/${id}`, "PATCH", body);

  /** What puts a scene's fields back as they were before `body` changed them ("Hoàn tác"). */
  function backOf(target: SceneData, body: Record<string, unknown>): Record<string, unknown> {
    const back: Record<string, unknown> = {};
    for (const key of Object.keys(body)) {
      if (key === "seconds" || key === "seconds_auto") {
        back.seconds = target.seconds;
        back.seconds_auto = target.seconds_auto;
      } else if (key === "video_start") back.video_start = target.video?.start ?? 0;
      else if (key === "text") back.text = target.text;
      else if (key === "text_position") back.text_position = target.text_position;
    }
    return back;
  }

  /** A change to one scene made in the preview, kept for "Hoàn tác". */
  function changeScene(label: string, target: SceneData, body: Record<string, unknown>) {
    return history.run({ label, redo: patchOf(target.id, body), undo: patchOf(target.id, backOf(target, body)) });
  }
  const patchScene = (body: Record<string, unknown>) => changeScene("sửa cảnh", scene, body);

  /** A text box dropped on the stage: this scene's own place, or the place of every content scene. */
  function dropBox(centre: [number, number]) {
    const point: [number, number] = [Math.round(centre[0]), Math.round(centre[1])];
    const target = scene;
    const done = () => setDragged(null);
    if (scope === "scene" || target.is_title) {
      void changeScene("di chuyển chữ", target, { text_position: point }).finally(done);
      return;
    }
    const before = video.options.text_position;
    void history
      .run({
        label: "di chuyển chữ mọi cảnh",
        redo: async () => {
          const saved = await api<VideoDetail>(`/videos/${target.video_id}`, "PATCH", {
            options: { text_position: point },
          });
          return target.text_position ? patchOf(target.id, { text_position: null })() : saved;
        },
        undo: async () => {
          const saved = await api<VideoDetail>(`/videos/${target.video_id}`, "PATCH", {
            options: { text_position: before },
          });
          return target.text_position ? patchOf(target.id, { text_position: target.text_position })() : saved;
        },
      })
      .finally(done);
  }

  /** "Chuyển cảnh" is the video's: kept for "Hoàn tác" like the scenes' changes. */
  function changeTransition(next: VideoOptions["transition"]) {
    const before = video.options.transition;
    if (next === before) return;
    void history.run({
      label: "đổi chuyển cảnh",
      redo: () => api<VideoDetail>(`/videos/${video.id}`, "PATCH", { options: { transition: next } }),
      undo: () => api<VideoDetail>(`/videos/${video.id}`, "PATCH", { options: { transition: before } }),
    });
  }

  /** The content scenes' new order, from dragging a segment of the bar. */
  function reorder(ids: number[]) {
    const before = video.scenes.map((item) => item.id);
    void history.run({
      label: "đổi thứ tự cảnh",
      redo: () => api<VideoDetail>(`/videos/${video.id}/scene-order`, "PUT", { ids }),
      undo: () => api<VideoDetail>(`/videos/${video.id}/scene-order`, "PUT", { ids: before }),
    });
  }

  /** A new empty scene right after the one shown, then shown itself, paused for editing. */
  async function addAfter() {
    const current = scene;
    await save(async () => {
      const added = await api<VideoDetail>(`/videos/${video.id}/scenes`, "POST");
      const fresh = added.scenes.at(-1);
      if (!fresh) return added;
      const ids = added.scenes.map((item) => item.id).filter((id) => id !== fresh.id);
      const at = current.is_title ? 0 : ids.indexOf(current.id) + 1;
      ids.splice(at, 0, fresh.id);
      return api<VideoDetail>(`/videos/${video.id}/scene-order`, "PUT", { ids });
    });
  }

  async function removeScene() {
    const index = phase.index;
    if (await save(() => api<VideoDetail>(`/scenes/${scene.id}`, "DELETE"))) {
      goTo(Math.max(0, index - 1), false);
      setPlaying(false);
    }
  }

  function replaceMedia(file: File) {
    const target = scene;
    void save(() =>
      file.type.startsWith("video/")
        ? upload<VideoDetail>(`/scenes/${target.id}/video`, file)
        : upload<VideoDetail>(`/scenes/${target.id}/image`, file),
    );
  }
  // The box follows the pointer only while the preview stands still on a scene.
  const still = !playing || ended;
  const canDrag = editable && still;

  // The current box, where it is (or is being dragged to), and what of the chosen app would cover it.
  const boxSize = scene?.textbox_url ? boxes[scene.textbox_url] : undefined;
  const boxCorner =
    boxSize && scene
      ? placeBox(boxSize, dragged?.sceneId === scene.id ? dragged.centre : scene.placed_at, scene.is_title)
      : null;
  const covered = boxSize && boxCorner ? coveredBy(platform, boxCorner, boxSize) : [];
  const snapped = dragged && scene && dragged.sceneId === scene.id ? dragged.centre : null;

  // Shortcuts while the drawer is open, unless a field is being typed in: Space plays or pauses, the arrows change
  // scene, [ and ] take or add a tenth of a second, Ctrl+Z / Ctrl+Shift+Z (or Ctrl+Y) undo and redo.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target instanceof HTMLElement ? event.target : null;
      if (target && (target.closest("input, textarea, select, [contenteditable=true]") || target.isContentEditable)) {
        return;
      }
      const mod = event.metaKey || event.ctrlKey;
      if (mod && event.key.toLowerCase() === "z") {
        event.preventDefault();
        void (event.shiftKey ? history.redo() : history.undo());
      } else if (mod && event.key.toLowerCase() === "y") {
        event.preventDefault();
        void history.redo();
      } else if (event.key === " " && !(target instanceof HTMLButtonElement)) {
        event.preventDefault();
        toggle();
      } else if (event.key === "ArrowLeft" && phase.index > 0) {
        goTo(phase.index - 1, false);
      } else if (event.key === "ArrowRight" && phase.index < scenes.length - 1) {
        goTo(phase.index + 1, false);
      } else if ((event.key === "[" || event.key === "]") && editable && scene) {
        const next = Math.round((scene.seconds + (event.key === "]" ? 0.1 : -0.1)) * 10) / 10;
        if (next >= 1 && next <= 10) void changeScene("đổi số giây", scene, { seconds: next });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

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
        <Flex gap={8} align="flex-start">
          {editable && still && scene && (
            <PreviewToolbar
              editable={editable}
              isTitle={scene.is_title}
              canUndo={history.canUndo}
              canRedo={history.canRedo}
              undoLabel={history.undoLabel}
              redoLabel={history.redoLabel}
              transition={video.options.transition}
              onUndo={() => void history.undo()}
              onRedo={() => void history.redo()}
              onMedia={replaceMedia}
              onTransition={changeTransition}
              onAddAfter={() => void addAfter()}
              onDelete={() => void removeScene()}
            />
          )}
          <Flex vertical gap={10} align="center">
            {/* A real phone's geometry around the frame: the 9:16 video sits under the status bar, as the apps show it. */}
            <Phone width={width} frame="pro" dark wallpaper="#000" time={statusTime}>
              <div
                ref={stage}
                data-testid="preview-stage"
                // A quick swipe across the phone (a finger or the mouse) moves to the next or the previous scene.
                onPointerDown={(event) => {
                  swipe.current = { x: event.clientX, y: event.clientY, at: performance.now() };
                }}
                onPointerUp={(event) => {
                  const start = swipe.current;
                  swipe.current = null;
                  if (!start || dragged || typing) return;
                  const dx = event.clientX - start.x;
                  const dy = event.clientY - start.y;
                  if (Math.abs(dx) > 60 && Math.abs(dy) < 50 && performance.now() - start.at < 600) {
                    const next = phase.index + (dx < 0 ? 1 : -1);
                    if (next >= 0 && next < scenes.length) goTo(next, false);
                  }
                }}
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
                    stage={stage}
                    centre={dragged?.sceneId === scene.id ? dragged.centre : null}
                    onDrag={canDrag ? (centre) => setDragged({ sceneId: scene.id, centre }) : undefined}
                    onDrop={canDrag ? dropBox : undefined}
                    onEditText={canDrag ? () => setTyping({ sceneId: scene.id, value: scene.text }) : undefined}
                    warn={covered.length > 0}
                    seekTo={seek}
                  />
                )}
                {/* Guides while dragging: the frame's middle, which the box snaps to when it comes near. */}
                {snapped && snapped[0] === FRAME_WIDTH / 2 && <span data-testid="guide-x" style={guideStyle("x")} />}
                {snapped && snapped[1] === FRAME_HEIGHT / 2 && <span data-testid="guide-y" style={guideStyle("y")} />}
                {typing && scene && typing.sceneId === scene.id && boxCorner && boxSize && (
                  <textarea
                    aria-label="Chữ trên màn hình"
                    autoFocus
                    // Opened with the whole text chosen, so typing replaces it and an arrow key keeps it.
                    onFocus={(event) => event.currentTarget.select()}
                    value={typing.value}
                    onChange={(event) => setTyping({ sceneId: scene.id, value: event.target.value })}
                    onKeyDown={(event) => {
                      if (event.key === "Escape") {
                        event.stopPropagation();
                        setTyping(null);
                      } else if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                        event.currentTarget.blur();
                      }
                    }}
                    onBlur={() => {
                      const value = typing.value;
                      setTyping(null);
                      if (value !== scene.text) void changeScene("sửa chữ", scene, { text: value });
                    }}
                    style={{
                      position: "absolute",
                      left: percent(boxCorner[0], FRAME_WIDTH),
                      top: percent(boxCorner[1], FRAME_HEIGHT),
                      width: percent(Math.max(boxSize.width, 560), FRAME_WIDTH),
                      minHeight: percent(boxSize.height, FRAME_HEIGHT),
                      zIndex: 3,
                      padding: 6,
                      fontSize: 13,
                      lineHeight: 1.4,
                      borderRadius: 6,
                      border: `2px solid ${COLORS.primary}`,
                      background: "rgba(255, 255, 255, 0.95)",
                      resize: "vertical",
                      fontFamily: "inherit",
                    }}
                  />
                )}
                {platform !== "none" && (
                  <PlatformFrame platform={platform} channel={channel} caption={caption} music={sound} />
                )}
                {guide && <SafeZone />}
              </div>
            </Phone>
            {covered.length > 0 && (
              <Typography.Text
                type="danger"
                style={{ fontSize: 12, alignSelf: "stretch", maxWidth: width }}
                data-testid="preview-covered"
              >
                Hộp chữ bị {covered.join(" và ")} của {PLATFORM_LABELS[platform as Platform]} che. Kéo chữ vào giữa hơn.
              </Typography.Text>
            )}
            <PreviewTimeline
              scenes={scenes}
              current={phase.index}
              run={phase.run}
              running={playing && !ended}
              editable={editable}
              label={label}
              onJump={(index) => goTo(index, false)}
              onSeconds={(index, value) => void changeScene("đổi số giây", scenes[index], { seconds: value })}
              onFollowVoice={(index) => void changeScene("khớp lời đọc", scenes[index], { seconds_auto: true })}
              onReorder={reorder}
            />
            {scene?.video && still && (
              <ClipTrim
                key={`${scene.id}-${scene.video.start}-${scene.seconds}`}
                clip={scene.video}
                seconds={scene.seconds}
                editable={editable}
                onSeek={setSeek}
                onCommit={(part) =>
                  void changeScene("cắt clip", scene, { video_start: part.start, seconds: part.seconds }).finally(() =>
                    setSeek(null),
                  )
                }
              />
            )}
            <Flex justify="space-between" style={{ width: "100%" }}>
              <Typography.Text strong data-testid="preview-scene">
                {label(phase.index)}, {seconds(scene?.fitted_seconds ?? 0)} giây
              </Typography.Text>
              <Typography.Text type="secondary">
                {phase.index + 1}/{scenes.length} cảnh, {seconds(total)} giây
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
              <ListenVolume />
            </Space>
            {editable && (
              <Typography.Text type="secondary" style={{ fontSize: 12, textAlign: "center", maxWidth: width }}>
                Tạm dừng để sửa trên điện thoại: kéo hoặc bấm đúp vào chữ, kéo mép hay kéo cả đoạn trên thanh thời gian.
                Phím: cách để phát/dừng, ← → chuyển cảnh, [ ] bớt/thêm 0,1 giây, Ctrl+Z hoàn tác.
              </Typography.Text>
            )}
          </Flex>
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
          {scene && (
            <SceneEditor
              key={`${scene.id}-${scene.seconds}`}
              scene={scene}
              label={label(phase.index)}
              editable={editable}
              still={!playing || ended}
              scope={scope}
              onScope={setScope}
              onPatch={patchScene}
              onResetPosition={() =>
                void save(() => api<VideoDetail>(`/scenes/${scene.id}`, "PATCH", { text_position: null }))
              }
            />
          )}
          <Flex vertical gap={8} data-testid="preview-voice">
            <Typography.Text strong>Giọng đọc</Typography.Text>
            {/* The video's ElevenLabs voice, the same choice as "Thiết lập": a new one makes the narration again. */}
            <VoicePicker
              values={{ ...video.options, voice_enabled: video.voice_enabled }}
              disabled={!editable}
              onChange={({ voice_id }) =>
                void save(() => api<VideoDetail>(`/videos/${video.id}`, "PATCH", { options: { voice_id } }))
              }
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {voicing
                ? "ElevenLabs đang đọc các cảnh, xong sẽ tự dùng giọng thật."
                : missingVoice
                  ? `${unvoiced} cảnh chưa có giọng ElevenLabs (lời đọc mới hoặc vừa đổi giọng), đang đọc tạm bằng giọng trình duyệt.`
                  : "Mọi cảnh đã có giọng ElevenLabs. Đổi giọng thì các cảnh được đọc lại khi tạo giọng hoặc render."}
            </Typography.Text>
            {(missingVoice || voicing) && (
              <Popconfirm
                title="Tạo giọng thật bằng ElevenLabs?"
                description={`ElevenLabs đọc ${unvoiced} cảnh, tốn credit một lần. Render sau đó dùng lại, không tốn thêm.`}
                okText="Tạo giọng"
                cancelText="Thôi"
                onConfirm={onMakeVoices}
                disabled={voicing || Boolean(video.active_job)}
              >
                <Button block loading={voicing} disabled={!voicing && Boolean(video.active_job)}>
                  Tạo giọng ElevenLabs cho {unvoiced} cảnh
                </Button>
              </Popconfirm>
            )}
            {missingVoice && (
              <Collapse
                size="small"
                ghost
                items={[
                  {
                    key: "browser",
                    label: "Giọng tạm của trình duyệt",
                    children: (
                      <Flex vertical gap={8}>
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
                      </Flex>
                    ),
                  },
                ]}
              />
            )}
          </Flex>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Bản xem trước gần đúng, chưa phải MP4. Cảnh đã có giọng ElevenLabs (sau một lần render hoặc “Tạo giọng
            ElevenLabs”) dùng giọng đó, cảnh khác dùng giọng tiếng Việt miễn phí của trình duyệt. Phụ đề và cách trộn âm
            chỉ có khi render.
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
  stage,
  centre = null,
  onDrag,
  onDrop,
  onEditText,
  warn = false,
  seekTo = null,
}: {
  video: VideoDetail;
  scene: SceneData;
  playing: boolean;
  entering: boolean;
  atEnd?: boolean;
  boxes: Record<string, { width: number; height: number }>;
  onBox: (url: string, size: { width: number; height: number }) => void;
  /** With these, the box is dragged on the stage: its centre while moving, and where it is dropped. */
  stage?: React.RefObject<HTMLDivElement | null>;
  centre?: [number, number] | null;
  onDrag?: (centre: [number, number]) => void;
  onDrop?: (centre: [number, number]) => void;
  /** A double-click on the box: type its on-screen text in place. */
  onEditText?: () => void;
  /** The chosen app draws over the box: outlined in red. */
  warn?: boolean;
  /** The clip time to show while the trim bar is dragged; null plays the clip as the scene does. */
  seekTo?: number | null;
}) {
  const grab = useRef<{ dx: number; dy: number; last: [number, number] | null } | null>(null);
  // A finger holds the box a moment before it moves, so a quick swipe still changes scene.
  const hold = useRef<{ timer: number; x: number; y: number; armed: boolean } | null>(null);
  const clipRef = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const element = clipRef.current;
    if (element && seekTo !== null) {
      element.pause();
      element.currentTime = seekTo;
    }
  }, [seekTo]);
  const { transition, motion, zoom } = video.options;
  const end = ZOOMS[zoom];
  // The frame without text when there is one, so the box stays still while the picture moves; else the preview.
  const picture = scene.frame_url ?? scene.preview_url;
  const box = scene.frame_url ? scene.textbox_url : null;
  const size = box ? boxes[box] : undefined;
  const corner = size ? placeBox(size, centre ?? scene.placed_at, scene.is_title) : null;

  /** The pointer in frame pixels (1080 × 1920). */
  function framePoint(event: React.PointerEvent): [number, number] | null {
    const rect = stage?.current?.getBoundingClientRect();
    if (!rect) return null;
    return [
      ((event.clientX - rect.left) / rect.width) * FRAME_WIDTH,
      ((event.clientY - rect.top) / rect.height) * FRAME_HEIGHT,
    ];
  }
  const dragHandlers =
    onDrag && onDrop && size && corner
      ? {
          onPointerDown: (event: React.PointerEvent<HTMLImageElement>) => {
            const point = framePoint(event);
            if (!point) return;
            const target = event.currentTarget;
            const pointerId = event.pointerId;
            const start = () => {
              target.setPointerCapture(pointerId);
              grab.current = { dx: point[0] - corner[0], dy: point[1] - corner[1], last: null };
            };
            if (event.pointerType === "touch") {
              hold.current = {
                x: event.clientX,
                y: event.clientY,
                armed: false,
                timer: window.setTimeout(() => {
                  if (hold.current) hold.current.armed = true;
                  start();
                }, 350),
              };
              return;
            }
            event.preventDefault();
            event.stopPropagation();
            start();
          },
          onPointerMove: (event: React.PointerEvent<HTMLImageElement>) => {
            const pending = hold.current;
            if (pending && !pending.armed && Math.hypot(event.clientX - pending.x, event.clientY - pending.y) > 10) {
              window.clearTimeout(pending.timer);
              hold.current = null;
              return;
            }
            const point = framePoint(event);
            if (!grab.current || !point) return;
            event.stopPropagation();
            // The box's centre; placeBox keeps it inside the safe zone, and the title stays centred across.
            const next: [number, number] = [
              scene.is_title ? FRAME_WIDTH / 2 : point[0] - grab.current.dx + size.width / 2,
              point[1] - grab.current.dy + size.height / 2,
            ];
            const placed = placeBox(size, next, scene.is_title);
            const kept: [number, number] = [placed[0] + size.width / 2, placed[1] + size.height / 2];
            // Near the frame's middle it snaps there, and a guide shows it (see VideoPreview).
            if (Math.abs(kept[0] - FRAME_WIDTH / 2) < SNAP) kept[0] = FRAME_WIDTH / 2;
            if (Math.abs(kept[1] - FRAME_HEIGHT / 2) < SNAP) kept[1] = FRAME_HEIGHT / 2;
            grab.current.last = kept;
            onDrag(kept);
          },
          onPointerUp: (event: React.PointerEvent<HTMLImageElement>) => {
            if (hold.current) window.clearTimeout(hold.current.timer);
            hold.current = null;
            const last = grab.current?.last;
            grab.current = null;
            if (last) {
              event.stopPropagation();
              onDrop(last);
            }
          },
          onDoubleClick: onEditText,
        }
      : {};
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
          ref={clipRef}
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
          {...dragHandlers}
          data-testid={onDrag ? "preview-textbox" : undefined}
          draggable={false}
          style={{
            position: "absolute",
            visibility: corner ? "visible" : "hidden",
            left: corner ? percent(corner[0], FRAME_WIDTH) : 0,
            top: corner ? percent(corner[1], FRAME_HEIGHT) : 0,
            width: size ? percent(size.width, FRAME_WIDTH) : undefined,
            cursor: onDrag ? "grab" : undefined,
            touchAction: onDrag ? "none" : undefined,
            outline: warn ? "2px solid #ff4d4f" : onDrag ? "1px dashed rgba(255, 255, 255, 0.7)" : undefined,
            outlineOffset: 4,
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

/**
 * "Chỉnh cảnh này": the scene's seconds (or "Tự khớp lời đọc"), the part of its clip it shows, and where its text
 * sits, saved at once as on the scene cards. Shown while the preview stands still, read-only while the page is.
 */
function SceneEditor({
  scene,
  label,
  editable,
  still,
  scope,
  onScope,
  onPatch,
  onResetPosition,
}: {
  scene: SceneData;
  label: string;
  editable: boolean;
  still: boolean;
  scope: "scene" | "all";
  onScope: (scope: "scene" | "all") => void;
  onPatch: (body: Record<string, unknown>) => Promise<void>;
  onResetPosition: () => void;
}) {
  // Started from the saved seconds; the drawer keys this panel on the scene and its seconds, so a save resets it.
  const [typed, setTyped] = useState<number | null>(scene.seconds);
  const clip = scene.video;
  const speed = clip?.speed ?? 1;
  // The clip's part on screen: from its start, as long as the scene at the clip's speed.
  const until = clip ? Math.min(clip.seconds, clip.start + scene.seconds * speed) : 0;
  const commit = () => {
    if (typed !== null && typed !== scene.seconds) {
      void onPatch({ seconds: typed });
    }
  };
  return (
    <Flex vertical gap={10} data-testid="preview-scene-editor">
      <Typography.Text strong>Chỉnh {label.toLowerCase()}</Typography.Text>
      {!editable && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Bấm “Chỉnh sửa” trên trang video (và chờ job xong) để sửa ngay tại đây.
        </Typography.Text>
      )}
      <Flex align="center" gap={8} wrap>
        <InputNumber
          aria-label="Số giây của cảnh"
          min={1}
          max={10}
          step={0.1}
          precision={1}
          value={typed}
          disabled={!editable}
          onChange={setTyped}
          onBlur={commit}
          onPressEnter={commit}
          suffix="giây"
          style={{ width: 110 }}
        />
        <Flex align="center" gap={6}>
          <Switch
            size="small"
            aria-label="Tự khớp lời đọc"
            checked={scene.seconds_auto}
            disabled={!editable}
            onChange={(checked) => void onPatch({ seconds_auto: checked })}
          />
          <Typography.Text style={{ fontSize: 13 }}>Tự khớp lời đọc</Typography.Text>
        </Flex>
      </Flex>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {scene.voice_seconds !== null
          ? `Lời đọc dài ${seconds(scene.voice_seconds)} giây${
              scene.fitted_seconds > scene.seconds ? `, cảnh kéo dài thành ${seconds(scene.fitted_seconds)} giây` : ""
            }.`
          : scene.seconds_auto
            ? "Có giọng ElevenLabs là số giây tự theo lời đọc."
            : "Gõ số giây là cảnh giữ đúng số đó; bật “Tự khớp lời đọc” để theo lời đọc."}
      </Typography.Text>
      {clip && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Đoạn clip: từ {seconds(clip.start)} đến {seconds(until)} giây. Kéo khung trên dải dưới điện thoại để cắt.
        </Typography.Text>
      )}
      {scene.textbox_url && (
        <Flex vertical gap={6}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {still && editable
              ? "Kéo hộp chữ trên màn hình để đổi chỗ (trên điện thoại: chạm giữ rồi kéo), bấm đúp để sửa chữ."
              : "Tạm dừng ở cảnh này để kéo hộp chữ."}
          </Typography.Text>
          {!scene.is_title && (
            <Flex align="center" gap={8} wrap>
              <Segmented
                size="small"
                aria-label="Áp dụng vị trí chữ"
                value={scope}
                onChange={(value) => onScope(value as "scene" | "all")}
                options={[
                  { value: "scene", label: "Cảnh này" },
                  { value: "all", label: "Mọi cảnh" },
                ]}
                disabled={!editable}
              />
              {scene.text_position && (
                <Button size="small" type="link" disabled={!editable} onClick={onResetPosition}>
                  Về vị trí chung
                </Button>
              )}
            </Flex>
          )}
        </Flex>
      )}
    </Flex>
  );
}
