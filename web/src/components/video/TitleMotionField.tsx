"use client";

import { Alert, App, Button, Checkbox, Flex, Input, Segmented, Select, Typography } from "antd";
import { useState } from "react";
import { api, errorMessage, type SceneData, type VideoDetail, upload } from "@/lib/api";
import { useSentImage } from "@/lib/googleExtension";
import { looksLikeClipLink, unwrapLink, fileFromDataUrl } from "@/lib/mediaLinks";
import { useEditor } from "./AutoSaveField";
import TitleSlotPhoto from "./TitleSlotPhoto";

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_IMAGE_BYTES = 15 * 1024 * 1024;

const LAYOUTS = { grid: "lưới", ring: "vòng", strip: "dải", warn: "món nên tránh" } as const;
type Choice = "auto" | keyof typeof LAYOUTS;
const CHOICES: { value: Choice; label: string }[] = [
  { value: "auto", label: "Tự động" },
  { value: "grid", label: "Lưới (2–6 món)" },
  { value: "ring", label: "Vòng (5–9 món)" },
  { value: "strip", label: "Dải (7–10 món)" },
  { value: "warn", label: "Món nên tránh (2–6 món)" },
];

/**
 * "Tiêu đề động" of the title scene (api title_motion.py): a 3-second title where the listed dishes' photos pop in
 * one by one, built from the scenes below it. "Kiểu tiêu đề" switches between it and the title's own photo or clip
 * without a new render; the button builds it again after the dishes, their photos or their number change.
 */
export default function TitleMotionField({ scene, disabled }: { scene: SceneData; disabled: boolean }) {
  const editor = useEditor();
  const { message } = App.useApp();
  const made = scene.title_motion;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [writeHook, setWriteHook] = useState(false);
  // The layout asked for: the member's pick, else the one the title was built with ("auto" for a new one).
  const [picked, setPicked] = useState<Choice | null>(null);
  const layout: Choice = picked ?? made?.requested ?? "auto";
  // Names the member typed into a slot, by its place; the others keep following their scene.
  const [edited, setEdited] = useState<Record<number, string>>({});

  // "Gửi ảnh vào Reels Studio" while a slot is the one being filled arrives here instead of at the scene.
  useSentImage(scene.id, (url, cell) => (cell === null ? undefined : void assignLink(cell, url)), true);

  if (!scene.is_title || editor.readOnly) {
    return null;
  }
  const off = disabled || busy || Boolean(made?.pending);

  async function build() {
    setBusy(true);
    setError(null);
    try {
      const done = await api<{ video: VideoDetail; warnings: string[] }>(`/title-motion/${scene.id}`, "POST", {
        layout,
        write_hook: writeHook,
        slots: made?.labels.map((_, index) => (edited[index]?.trim() ? { label: edited[index] } : {})),
      });
      setWarnings(done.warnings);
      editor.onSaved(done.video);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  /** A photo of the member's own for one slot; it shows from the next "Dựng lại tiêu đề". */
  async function slotPhoto(index: number, send: () => Promise<VideoDetail>, done?: string) {
    setBusy(true);
    setError(null);
    try {
      editor.onSaved(await send());
      const name = (edited[index] ?? made?.labels[index] ?? "").trim();
      void message.success(done ?? `Đã gán ảnh cho ô ${index + 1}${name ? `: ${name}` : ""}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  /** A chosen, dropped or pasted file, checked like the api does before it is sent. */
  function assignFile(index: number, file: File) {
    if (!IMAGE_TYPES.includes(file.type)) {
      void message.error(file.type.startsWith("video/") ? "Ô tiêu đề chỉ nhận ảnh" : "Chỉ nhận ảnh JPG, PNG hoặc WebP");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      void message.error("Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn");
      return;
    }
    void slotPhoto(index, () => upload<VideoDetail>(`/title-motion/${scene.id}/slots/${index}/photo`, file));
  }

  /** A photo's link (or a data: photo); a video's link is refused, a slot holds a photo only. */
  async function assignLink(index: number, text: string) {
    const link = unwrapLink(text.trim());
    if (/^data:image\//i.test(link)) {
      assignFile(index, await fileFromDataUrl(link));
      return;
    }
    if (looksLikeClipLink(link)) {
      void message.error("Ô tiêu đề chỉ nhận ảnh");
      return;
    }
    void slotPhoto(index, () =>
      api<VideoDetail>(`/title-motion/${scene.id}/slots/${index}/photo-link`, "POST", { url: link }),
    );
  }

  async function switchTo(mode: "classic" | "motion") {
    setBusy(true);
    setError(null);
    try {
      editor.onSaved(await api<VideoDetail>(`/title-motion/${scene.id}/mode`, "POST", { mode }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Flex vertical gap={6} data-testid="title-motion">
      <Flex align="center" gap={8} wrap>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Tiêu đề động
        </Typography.Text>
        <Button size="small" loading={busy || Boolean(made?.pending)} disabled={off} onClick={() => void build()}>
          {made ? "Dựng lại tiêu đề" : "Tạo tiêu đề động"}
        </Button>
        <Select
          size="small"
          aria-label="Bố cục tiêu đề"
          value={layout}
          options={CHOICES}
          disabled={off}
          style={{ width: 190 }}
          onChange={(value) => setPicked(value)}
        />
        <Checkbox checked={writeHook} disabled={off} onChange={(event) => setWriteHook(event.target.checked)}>
          Viết lại chữ tiêu đề theo mẫu
        </Checkbox>
        {made?.pending && <Typography.Text type="secondary">Đang dựng, chờ khoảng 1–3 phút</Typography.Text>}
      </Flex>
      {made && !made.pending && (
        <Flex align="center" gap={8} wrap>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Kiểu tiêu đề
          </Typography.Text>
          <Segmented
            size="small"
            aria-label="Kiểu tiêu đề"
            value={made.mode}
            disabled={off}
            options={[
              { label: "Cổ điển", value: "classic", disabled: !made.has_classic && made.mode === "motion" },
              { label: "Động", value: "motion", disabled: !made.ready },
            ]}
            onChange={(value) => void switchTo(value as "classic" | "motion")}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {made.count} món, bố cục {LAYOUTS[made.layout]}
          </Typography.Text>
        </Flex>
      )}
      {made && !made.pending && made.labels.length > 0 && (
        <Flex vertical gap={4} data-testid="title-slots">
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Tên các ô (sửa rồi bấm “Dựng lại tiêu đề”)
          </Typography.Text>
          <div className="title-cells">
            {made.labels.map((label, index) => (
              <div key={index} className="title-cells__item">
                <Input
                  size="small"
                  maxLength={22}
                  aria-label={`Tên ô ${index + 1}`}
                  value={edited[index] ?? label}
                  disabled={off}
                  onChange={(event) => setEdited({ ...edited, [index]: event.target.value })}
                />
                <TitleSlotPhoto
                  title={scene}
                  index={index}
                  name={edited[index] ?? label}
                  photoUrl={made.slots?.[index]?.photo_url ?? null}
                  from={made.slots?.[index]?.from_scene ?? null}
                  disabled={off}
                  onFile={(file) => assignFile(index, file)}
                  onLink={(text) => assignLink(index, text)}
                  onLibrary={(mediaId) =>
                    api<VideoDetail>(`/title-motion/${scene.id}/slots/${index}/photo-library`, "POST", {
                      media_id: mediaId,
                    })
                  }
                  onRemove={() =>
                    void slotPhoto(
                      index,
                      () => api<VideoDetail>(`/title-motion/${scene.id}/slots/${index}/photo`, "DELETE"),
                      "Đã xóa ảnh của ô",
                    )
                  }
                />
              </div>
            ))}
          </div>
        </Flex>
      )}
      {warnings.map((line) => (
        <Alert key={line} type="warning" showIcon title={line} />
      ))}
      {error && <Alert type="error" showIcon title={error} />}
    </Flex>
  );
}
