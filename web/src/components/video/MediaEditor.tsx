"use client";

import { PlayCircleOutlined, RedoOutlined, SwapOutlined, UndoOutlined } from "@ant-design/icons";
import { Alert, Button, Flex, Modal, Slider, Switch, Typography } from "antd";
import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import Cropper, { type Area } from "react-easy-crop";
import ListenVolume, { useListen } from "@/components/ListenVolume";
import { api, errorMessage, upload, type SceneData, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

// The template's frame: a crop smaller than this is stretched by the render and looks soft.
const FRAME_WIDTH = 1080;
const FRAME_HEIGHT = 1920;
// The api's limits for a clip scene (script_rules.py: MIN_SECONDS, MAX_SECONDS; routes_videos.py:
// MAX_CLIP_SCENE_SECONDS) and the part of the clip each crossfade plays into (CROSSFADE_SIDE_SECONDS).
const MIN_SCENE_SECONDS = 1;
const MAX_CLIP_SCENE_SECONDS = 10;
const CROSSFADE_SIDE_SECONDS = 0.2;
// reels_render/script.py: MIN_VIDEO_SPEED, MAX_VIDEO_SPEED.
const MIN_CLIP_SPEED = 0.5;
const MAX_CLIP_SPEED = 2;

const round = (value: number, digits: number) => Number(value.toFixed(digits));
const seconds = (value: number) => value.toLocaleString("vi-VN", { maximumFractionDigits: 1 });
const speedText = (value: number) => `${value.toLocaleString("vi-VN")}×`;

/** "Chỉnh khung": a photo is cropped to 9:16, turned or flipped; a clip is trimmed to the part the scene plays. */
export default function MediaEditor({
  scene,
  voiceEnabled,
  onClose,
}: {
  scene: SceneData;
  voiceEnabled: boolean;
  onClose: () => void;
}) {
  const which = scene.is_title ? "cảnh tiêu đề" : "cảnh";
  return scene.video ? (
    <ClipTrim scene={scene} clip={scene.video} voiceEnabled={voiceEnabled} which={which} onClose={onClose} />
  ) : (
    <PhotoCrop scene={scene} which={which} onClose={onClose} />
  );
}

// Both dialogs sit in the middle of the screen, the picture on the left and its controls beside it (under it on a
// phone), so nothing needs scrolling to reach "Áp dụng".
const DIALOG = {
  centered: true,
  width: 860,
  styles: { body: { maxHeight: "calc(100vh - 180px)", overflowY: "auto", overflowX: "hidden" } },
} as const;
const MEDIA_HEIGHT = "min(56vh, 480px)";

function EditorLayout({ media, children }: { media: ReactNode; children: ReactNode }) {
  return (
    <Flex wrap gap={24} align="flex-start">
      <div style={{ flex: "1 1 340px", minWidth: 0 }}>{media}</div>
      <Flex vertical gap={16} style={{ flex: "1 1 260px", minWidth: 0 }}>
        {children}
      </Flex>
    </Flex>
  );
}

function Section({ label, extra, children }: { label: string; extra?: ReactNode; children: ReactNode }) {
  return (
    <Flex vertical gap={6}>
      <Flex justify="space-between" align="center" gap={8}>
        <Typography.Text strong>{label}</Typography.Text>
        {extra}
      </Flex>
      {children}
    </Flex>
  );
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Không mở được ảnh của cảnh"));
    image.src = src;
  });
}

/**
 * The crop as a JPEG of at most 1080×1920. The photo is turned and flipped around its centre on a canvas the size of
 * its turned bounds, the same way react-easy-crop shows it, so the crop's pixel area applies to that canvas as is.
 */
async function cropToJpeg(src: string, area: Area, rotation: number, flipped: boolean): Promise<File> {
  const image = await loadImage(src);
  const turn = (rotation * Math.PI) / 180;
  const sin = Math.abs(Math.sin(turn));
  const cos = Math.abs(Math.cos(turn));
  const turned = document.createElement("canvas");
  turned.width = Math.round(image.width * cos + image.height * sin);
  turned.height = Math.round(image.width * sin + image.height * cos);
  const draw = turned.getContext("2d");
  if (!draw) {
    throw new Error("Trình duyệt không vẽ được ảnh");
  }
  draw.translate(turned.width / 2, turned.height / 2);
  draw.rotate(turn);
  draw.scale(flipped ? -1 : 1, 1);
  draw.translate(-image.width / 2, -image.height / 2);
  draw.drawImage(image, 0, 0);

  const scale = Math.min(1, FRAME_WIDTH / area.width);
  const out = document.createElement("canvas");
  out.width = Math.round(area.width * scale);
  out.height = Math.round(area.height * scale);
  out.getContext("2d")?.drawImage(turned, area.x, area.y, area.width, area.height, 0, 0, out.width, out.height);
  const blob = await new Promise<Blob | null>((resolve) => out.toBlob(resolve, "image/jpeg", 0.9));
  if (!blob) {
    throw new Error("Trình duyệt không xuất được ảnh đã cắt");
  }
  return new File([blob], "crop.jpg", { type: "image/jpeg" });
}

function PhotoCrop({ scene, which, onClose }: { scene: SceneData; which: string; onClose: () => void }) {
  const editor = useEditor();
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [area, setArea] = useState<Area | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const src = scene.image_url;
  const soft = area !== null && area.width < FRAME_WIDTH;

  async function apply() {
    if (!src || !area) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const file = await cropToJpeg(src, area, rotation, flipped);
      editor.onSaved(await upload<VideoDetail>(`/scenes/${scene.id}/image/crop`, file));
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  function reset() {
    setCrop({ x: 0, y: 0 });
    setZoom(1);
    setRotation(0);
    setFlipped(false);
  }

  return (
    <Modal
      open
      {...DIALOG}
      title={`Chỉnh khung ảnh ${which}`}
      onCancel={onClose}
      onOk={apply}
      okText="Áp dụng"
      cancelText="Huỷ"
      okButtonProps={{ disabled: !area, loading: saving }}
      cancelButtonProps={{ disabled: saving }}
      maskClosable={!saving}
      destroyOnHidden
    >
      <EditorLayout
        media={
          <div
            style={{
              position: "relative",
              height: MEDIA_HEIGHT,
              background: "#141414",
              borderRadius: 8,
              overflow: "hidden",
            }}
          >
            {src && (
              <Cropper
                image={src}
                crop={crop}
                zoom={zoom}
                rotation={rotation}
                aspect={9 / 16}
                maxZoom={4}
                // The flip is shown with the same transform the crop is drawn with.
                transform={`translate(${crop.x}px, ${crop.y}px) rotate(${rotation}deg) scale(${flipped ? -zoom : zoom}, ${zoom})`}
                onCropChange={setCrop}
                onZoomChange={setZoom}
                onCropComplete={(_, pixels) => setArea(pixels)}
              />
            )}
          </div>
        }
      >
        <Typography.Text type="secondary">Kéo ảnh để chọn phần nằm trong khung 9:16.</Typography.Text>
        <Section label="Phóng to" extra={<Typography.Text type="secondary">{zoom.toFixed(2)}×</Typography.Text>}>
          <Slider
            aria-label="Phóng to"
            min={1}
            max={4}
            step={0.05}
            value={zoom}
            onChange={setZoom}
            tooltip={{ formatter: (value) => `${(value ?? 1).toFixed(2)}×` }}
          />
        </Section>
        <Section label="Xoay và lật">
          <Flex gap={8} wrap>
            <Button icon={<RedoOutlined />} onClick={() => setRotation((current) => (current + 90) % 360)}>
              Xoay 90°
            </Button>
            <Button icon={<SwapOutlined />} type={flipped ? "primary" : "default"} onClick={() => setFlipped(!flipped)}>
              Lật ngang
            </Button>
            <Button icon={<UndoOutlined />} onClick={reset}>
              Đặt lại
            </Button>
          </Flex>
        </Section>
        {soft && (
          <Alert
            type="warning"
            showIcon
            title={`Vùng cắt chỉ rộng ${Math.round(area.width)} điểm ảnh (khung là ${FRAME_WIDTH}×${FRAME_HEIGHT}): ảnh sẽ bị mờ khi phóng to.`}
            data-testid="crop-soft"
          />
        )}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Ảnh đã cắt thay ảnh hiện tại và giữ nguồn của nó (Pixabay, ảnh AI…). Muốn về ảnh gốc thì chọn lại ảnh.
        </Typography.Text>
        {error && (
          <Typography.Text type="danger" data-testid="crop-error">
            {error}
          </Typography.Text>
        )}
      </EditorLayout>
    </Modal>
  );
}

function ClipTrim({
  scene,
  clip,
  voiceEnabled,
  which,
  onClose,
}: {
  scene: SceneData;
  clip: NonNullable<SceneData["video"]>;
  voiceEnabled: boolean;
  which: string;
  onClose: () => void;
}) {
  const editor = useEditor();
  const player = useRef<HTMLVideoElement>(null);
  // The scene lasts `seconds`, plus a crossfade's worth on each side that has a neighbour; at a speed, each of those
  // seconds takes `speed` seconds of the clip.
  const sides = (scene.is_title ? 1 : 2) * CROSSFADE_SIDE_SECONDS;
  const total = clip.seconds;
  const [speed, setSpeed] = useState(clip.speed);
  // The end may lie past the clip: the scene keeps its seconds, its last frame holds, and the dialog warns.
  const [range, setRange] = useState<[number, number]>([
    clip.start,
    round(clip.start + (scene.seconds + sides) * clip.speed, 2),
  ]);
  const [sound, setSound] = useState(false);
  // "Nghe tiếng gốc" turns the clip's sound on; the listener's level sets how loud.
  const { factor: listen } = useListen();
  useEffect(() => {
    if (player.current) player.current.volume = listen;
  }, [listen]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [start, end] = range;
  const shownEnd = Math.min(end, total);
  const length = round((end - start) / speed - sides, 1);
  const problem =
    length < MIN_SCENE_SECONDS
      ? `Cảnh cần ít nhất ${seconds(MIN_SCENE_SECONDS)} giây: kéo hai đầu xa nhau hơn`
      : length > MAX_CLIP_SCENE_SECONDS
        ? `Cảnh dùng video dài tối đa ${MAX_CLIP_SCENE_SECONDS} giây: kéo hai đầu gần nhau hơn`
        : null;
  const short =
    end > total + 0.01
      ? `Ở tốc độ ${speedText(speed)} cảnh cần ${seconds(end - start)} giây clip nhưng từ điểm bắt đầu chỉ còn ${seconds(total - start)} giây: khung cuối sẽ đứng yên. Giảm tốc độ, rút ngắn cảnh hoặc lùi điểm bắt đầu.`
      : null;

  function change(next: number[]) {
    const [nextStart, nextEnd] = next as [number, number];
    // The player jumps to the handle being dragged, so the member sees the frame it stands on.
    if (player.current) {
      player.current.pause();
      player.current.currentTime = nextStart !== start ? nextStart : nextEnd;
    }
    setRange([nextStart, nextEnd === shownEnd ? end : nextEnd]);
  }

  // The scene keeps its seconds: a new speed moves the end of the part it takes from the clip.
  function changeSpeed(next: number) {
    setSpeed(next);
    setRange([start, round(start + (length + sides) * next, 2)]);
    if (player.current) {
      player.current.playbackRate = next;
    }
  }

  function preview() {
    const video = player.current;
    if (!video) {
      return;
    }
    video.currentTime = start;
    video.playbackRate = speed;
    void video.play();
  }

  async function apply() {
    setSaving(true);
    setError(null);
    try {
      editor.onSaved(
        await api<VideoDetail>(`/scenes/${scene.id}`, "PATCH", {
          video_start: round(start, 2),
          video_speed: speed,
          seconds: length,
        }),
      );
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open
      {...DIALOG}
      title={`Cắt video ${which}`}
      onCancel={onClose}
      onOk={apply}
      okText="Áp dụng"
      cancelText="Huỷ"
      okButtonProps={{ disabled: problem !== null, loading: saving }}
      cancelButtonProps={{ disabled: saving }}
      maskClosable={!saving}
      destroyOnHidden
    >
      <EditorLayout
        media={
          <video
            ref={player}
            src={clip.url}
            muted={!sound}
            playsInline
            preload="metadata"
            aria-label={`Xem trước video ${which}`}
            data-testid="trim-player"
            // "Xem thử" plays the chosen part only.
            onTimeUpdate={(event) => {
              if (event.currentTarget.currentTime >= shownEnd) {
                event.currentTarget.pause();
              }
            }}
            style={{
              display: "block",
              height: MEDIA_HEIGHT,
              maxWidth: "100%",
              aspectRatio: "9 / 16",
              margin: "0 auto",
              objectFit: "cover",
              background: "#000",
              borderRadius: 8,
            }}
          />
        }
      >
        <Section
          label="Đoạn dùng cho cảnh"
          extra={
            <Button size="small" icon={<PlayCircleOutlined />} onClick={preview}>
              Xem thử
            </Button>
          }
        >
          <Slider
            range
            aria-label="Đoạn video dùng cho cảnh"
            min={0}
            max={total}
            step={0.1}
            value={[start, shownEnd]}
            onChange={change}
            tooltip={{ formatter: (value) => `${seconds(value ?? 0)} giây` }}
          />
          <Typography.Text type="secondary" data-testid="trim-range">
            Từ giây {seconds(start)} đến {seconds(shownEnd)} · cảnh dài {seconds(length)} giây
          </Typography.Text>
        </Section>
        <Section
          label="Tốc độ clip"
          extra={<Typography.Text data-testid="trim-speed">{speedText(speed)}</Typography.Text>}
        >
          <Slider
            aria-label="Tốc độ clip"
            min={MIN_CLIP_SPEED}
            max={MAX_CLIP_SPEED}
            step={0.25}
            value={speed}
            onChange={changeSpeed}
            tooltip={{ formatter: (value) => speedText(value ?? 1) }}
          />
        </Section>
        {problem && <Alert type="error" showIcon title={problem} data-testid="trim-problem" />}
        {short && <Alert type="warning" showIcon title={short} data-testid="trim-short" />}
        <Section label="Tiếng gốc">
          <Flex align="center" gap={8} wrap>
            <Switch checked={sound} onChange={setSound} aria-label="Nghe tiếng gốc" />
            <Typography.Text>Nghe khi xem thử</Typography.Text>
            {sound && <ListenVolume width={100} />}
          </Flex>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Video xuất ra không dùng tiếng gốc.
          </Typography.Text>
        </Section>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Hai đầu đã chừa {seconds(sides * speed)} giây cho chuyển cảnh.
          {voiceEnabled && " Cảnh có thể dài hơn để khớp lời đọc."}
        </Typography.Text>
        {error && (
          <Typography.Text type="danger" data-testid="trim-error">
            {error}
          </Typography.Text>
        )}
      </EditorLayout>
    </Modal>
  );
}
