"use client";

import { CloseOutlined } from "@ant-design/icons";
import { Alert, Button, Flex, Input, Modal, Radio, Tabs, Typography } from "antd";
import { useEffect, useRef, useState, type PointerEvent } from "react";
import { api, errorMessage, type SceneData, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

// The api's limits (image_edit.py: MAX_BOXES, MIN_BOX, MAX_PROMPT).
const MAX_BOXES = 10;
const MIN_BOX = 0.004;
const MAX_PROMPT = 500;
const MEDIA_HEIGHT = "min(60vh, 520px)";

export type Box = [number, number, number, number];
type Engine = "lama" | "cloudflare" | "gemini";
type Tab = "erase" | "describe";

const clamp = (value: number) => Math.min(1, Math.max(0, value));

/**
 * "Sửa ảnh": the scene's photo changed by AI, through a job. "Xóa vùng" erases the boxes a member draws over a logo,
 * a watermark or a stray object (LaMa on the server, free, or Cloudflare); "Sửa theo mô tả" asks Gemini in words.
 * The photo from before the first edit is kept, so "Khôi phục ảnh gốc" on the card brings it back.
 */
export default function ImageEditModal({ scene, onClose }: { scene: SceneData; onClose: () => void }) {
  const editor = useEditor();
  const [tab, setTab] = useState<Tab>("erase");
  const [boxes, setBoxes] = useState<Box[]>([]);
  const [eraser, setEraser] = useState<Exclude<Engine, "gemini">>("lama");
  const [fill, setFill] = useState("");
  const [prompt, setPrompt] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // "Tìm chữ/logo tự động": a free job; the dialog follows it and adds the boxes it finds.
  const [finding, setFinding] = useState(false);
  const [found, setFound] = useState<string | null>(null);
  const which = scene.is_title ? "cảnh tiêu đề" : "cảnh";

  useEffect(() => {
    if (!finding) {
      return;
    }
    let open = true;
    const timer = window.setInterval(async () => {
      try {
        const video = await api<VideoDetail>(`/videos/${scene.video_id}`);
        const job = video.active_job;
        if (!open || (job?.kind === "image_marks" && job.scene_id === scene.id)) {
          return;
        }
        editor.onSaved(video);
        const now = [video.title_scene, ...video.scenes].find((item) => item?.id === scene.id);
        const marks = now?.image_marks ?? null;
        setFinding(false);
        if (marks === null) {
          setError("Không tìm được chữ trên ảnh này, hãy tự khoanh vùng (xem lý do ở Nhật ký job)");
        } else if (marks.length === 0) {
          setFound("Không thấy chữ hay logo có chữ nào. Logo không có chữ thì hãy tự khoanh.");
        } else {
          setBoxes((current) => [...current, ...marks].slice(0, MAX_BOXES));
          setFound(`Đã khoanh ${marks.length} vùng có chữ. Kiểm tra lại, bỏ khung nào không phải watermark.`);
        }
      } catch (err) {
        setFinding(false);
        setError(errorMessage(err));
      }
    }, 2000);
    return () => {
      open = false;
      window.clearInterval(timer);
    };
  }, [finding, scene.id, scene.video_id, editor]);

  async function findMarks() {
    setError(null);
    setFound(null);
    try {
      editor.onSaved(await api<VideoDetail>(`/scenes/${scene.id}/image-marks`, "POST"));
      setFinding(true);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const ready = tab === "erase" ? boxes.length > 0 : prompt.trim().length > 0;

  async function submit() {
    setSaving(true);
    setError(null);
    const body =
      tab === "erase"
        ? { engine: eraser, boxes, prompt: eraser === "cloudflare" ? fill.trim() : "" }
        : { engine: "gemini", prompt: prompt.trim() };
    try {
      editor.onSaved(await api<VideoDetail>(`/scenes/${scene.id}/image-edit`, "POST", body));
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
      centered
      width={860}
      title={`Sửa ảnh ${which}`}
      okText={tab === "erase" ? "Xóa vùng đã khoanh" : "Sửa ảnh"}
      cancelText="Huỷ"
      okButtonProps={{ disabled: !ready || finding, loading: saving }}
      onOk={() => void submit()}
      onCancel={onClose}
      styles={{ body: { maxHeight: "calc(100vh - 180px)", overflowY: "auto", overflowX: "hidden" } }}
    >
      <Flex wrap gap={24} align="flex-start">
        <div style={{ flex: "1 1 340px", minWidth: 0, display: "flex", justifyContent: "center" }}>
          <BoxCanvas
            src={scene.image_url ?? ""}
            alt={`Ảnh của ${which}`}
            boxes={boxes}
            drawing={tab === "erase"}
            onChange={setBoxes}
          />
        </div>
        <Flex vertical gap={16} style={{ flex: "1 1 260px", minWidth: 0 }}>
          <Tabs
            activeKey={tab}
            onChange={(key) => setTab(key as Tab)}
            items={[
              {
                key: "erase",
                label: "Xóa vùng",
                children: (
                  <Flex vertical gap={12}>
                    <Typography.Text type="secondary">
                      Kéo chuột (hoặc ngón tay) trên ảnh để khoanh logo, watermark hay vật cần xóa. Khoanh rộng hơn vật
                      một chút để xóa sạch viền.
                    </Typography.Text>
                    <Button onClick={() => void findMarks()} loading={finding} disabled={boxes.length >= MAX_BOXES}>
                      {finding ? "Đang tìm chữ/logo…" : "Tìm chữ/logo tự động"}
                    </Button>
                    {found && (
                      <Typography.Text type="secondary" data-testid="marks-found">
                        {found}
                      </Typography.Text>
                    )}
                    <Flex align="center" gap={8} wrap>
                      <Typography.Text data-testid="edit-box-count">
                        {boxes.length ? `Đã khoanh ${boxes.length} vùng` : "Chưa khoanh vùng nào"}
                      </Typography.Text>
                      {boxes.length > 0 && (
                        <Button size="small" onClick={() => setBoxes([])}>
                          Bỏ hết khung
                        </Button>
                      )}
                    </Flex>
                    <Radio.Group
                      value={eraser}
                      onChange={(event) => setEraser(event.target.value)}
                      aria-label="Cách xóa"
                    >
                      <Flex vertical gap={6}>
                        <Radio value="lama">Xóa nhanh (miễn phí, chạy trên máy chủ)</Radio>
                        <Radio value="cloudflare">Cloudflare (vẽ lại vùng theo mô tả nếu có)</Radio>
                      </Flex>
                    </Radio.Group>
                    {eraser === "cloudflare" && (
                      <Input
                        aria-label="Vẽ gì vào vùng đã khoanh"
                        placeholder="Không bắt buộc, ví dụ: mặt bàn gỗ (tiếng Anh cho kết quả tốt hơn)…"
                        maxLength={MAX_PROMPT}
                        value={fill}
                        onChange={(event) => setFill(event.target.value)}
                      />
                    )}
                  </Flex>
                ),
              },
              {
                key: "describe",
                label: "Sửa theo mô tả",
                children: (
                  <Flex vertical gap={12}>
                    <Typography.Text type="secondary">
                      Viết điều cần sửa, ví dụ: “làm nền sáng hơn”, “đổi nền thành bàn gỗ trong bếp”. Gemini sửa cả ảnh
                      và có thể đổi nhẹ chỗ khác; không ưng thì bấm “Khôi phục ảnh gốc”.
                    </Typography.Text>
                    <Input.TextArea
                      aria-label="Điều cần sửa trên ảnh"
                      autoSize={{ minRows: 3, maxRows: 6 }}
                      maxLength={MAX_PROMPT}
                      showCount
                      value={prompt}
                      onChange={(event) => setPrompt(event.target.value)}
                    />
                    <Alert type="warning" showIcon message="Mỗi lần sửa tốn phí Gemini của nhóm." />
                  </Flex>
                ),
              },
            ]}
          />
          {error && (
            <Typography.Text type="danger" data-testid="image-edit-error">
              {error}
            </Typography.Text>
          )}
        </Flex>
      </Flex>
    </Modal>
  );
}

/** The photo, with boxes drawn over it by dragging; each box has its own × to take it away. */
export function BoxCanvas({
  src,
  alt,
  boxes,
  drawing,
  onChange,
}: {
  src: string;
  alt: string;
  boxes: Box[];
  drawing: boolean;
  onChange: (boxes: Box[]) => void;
}) {
  const frame = useRef<HTMLDivElement>(null);
  const [start, setStart] = useState<[number, number] | null>(null);
  const [current, setCurrent] = useState<Box | null>(null);

  function point(event: PointerEvent): [number, number] {
    const rect = frame.current!.getBoundingClientRect();
    return [clamp((event.clientX - rect.left) / rect.width), clamp((event.clientY - rect.top) / rect.height)];
  }

  function boxFrom(from: [number, number], to: [number, number]): Box {
    const x = Math.min(from[0], to[0]);
    const y = Math.min(from[1], to[1]);
    return [x, y, Math.abs(to[0] - from[0]), Math.abs(to[1] - from[1])];
  }

  const full = boxes.length >= MAX_BOXES;

  return (
    <div
      ref={frame}
      data-testid="image-edit-canvas"
      style={{
        position: "relative",
        display: "inline-block",
        lineHeight: 0,
        touchAction: drawing ? "none" : "auto",
        cursor: drawing && !full ? "crosshair" : "default",
        userSelect: "none",
      }}
      onPointerDown={(event) => {
        if (!drawing || full || (event.target as HTMLElement).closest("button")) {
          return;
        }
        event.currentTarget.setPointerCapture(event.pointerId);
        const at = point(event);
        setStart(at);
        setCurrent([at[0], at[1], 0, 0]);
      }}
      onPointerMove={(event) => {
        if (start) {
          setCurrent(boxFrom(start, point(event)));
        }
      }}
      onPointerUp={(event) => {
        if (!start) {
          return;
        }
        const box = boxFrom(start, point(event));
        setStart(null);
        setCurrent(null);
        if (box[2] >= MIN_BOX * 2 && box[3] >= MIN_BOX * 2) {
          onChange([...boxes, box]);
        }
      }}
    >
      {/* A plain <img>: the photo as stored, so the boxes are fractions of exactly what the api edits. */}
      {/* eslint-disable-next-line @next/next/no-img-element -- the api's own photo, not an optimisable asset */}
      <img
        src={src}
        alt={alt}
        draggable={false}
        style={{ display: "block", maxWidth: "100%", maxHeight: MEDIA_HEIGHT, borderRadius: 6 }}
      />
      {boxes.map((box, index) => (
        <div key={index} data-testid="edit-box" style={boxStyle(box)}>
          <Button
            size="small"
            shape="circle"
            icon={<CloseOutlined />}
            aria-label={`Bỏ vùng ${index + 1}`}
            onClick={() => onChange(boxes.filter((_, other) => other !== index))}
            style={{ position: "absolute", top: -12, right: -12, lineHeight: 1 }}
          />
        </div>
      ))}
      {current && <div style={boxStyle(current)} />}
    </div>
  );
}

function boxStyle([x, y, width, height]: Box): React.CSSProperties {
  return {
    position: "absolute",
    left: `${x * 100}%`,
    top: `${y * 100}%`,
    width: `${width * 100}%`,
    height: `${height * 100}%`,
    border: "2px solid #FF4D4F",
    background: "rgba(255, 77, 79, 0.25)",
    boxSizing: "border-box",
  };
}
