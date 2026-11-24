"use client";

import { Alert, Button, Checkbox, Flex, Input, Popover, Segmented, Typography } from "antd";
import { useState } from "react";
import { api, errorMessage, type SceneData, type VideoDetail, upload } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

const LAYOUTS = { grid: "lưới", ring: "vòng", strip: "dải", warn: "món nên tránh" } as const;

/**
 * "Tiêu đề động" of the title scene (api title_motion.py): a 3-second title where the listed dishes' photos pop in
 * one by one, built from the scenes below it. "Kiểu tiêu đề" switches between it and the title's own photo or clip
 * without a new render; the button builds it again after the dishes, their photos or their number change.
 */
export default function TitleMotionField({ scene, disabled }: { scene: SceneData; disabled: boolean }) {
  const editor = useEditor();
  const made = scene.title_motion;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [writeHook, setWriteHook] = useState(false);
  // Names the member typed into a slot, by its place; the others keep following their scene.
  const [edited, setEdited] = useState<Record<number, string>>({});

  if (!scene.is_title || editor.readOnly) {
    return null;
  }
  const off = disabled || busy || Boolean(made?.pending);

  async function build() {
    setBusy(true);
    setError(null);
    try {
      const done = await api<{ video: VideoDetail; warnings: string[] }>(`/title-motion/${scene.id}`, "POST", {
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
  async function slotPhoto(index: number, send: () => Promise<VideoDetail>) {
    setBusy(true);
    setError(null);
    try {
      editor.onSaved(await send());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
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
                <Popover
                  trigger="click"
                  title={`Ảnh riêng cho ô ${index + 1}`}
                  content={
                    <Flex vertical gap={6} style={{ width: 240 }}>
                      <input
                        type="file"
                        accept="image/*"
                        aria-label={`Tải ảnh cho ô ${index + 1}`}
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          if (file) {
                            void slotPhoto(index, () =>
                              upload<VideoDetail>(`/title-motion/${scene.id}/slots/${index}/photo`, file),
                            );
                          }
                        }}
                      />
                      <Input.Search
                        size="small"
                        placeholder="Dán link ảnh"
                        enterButton="Lấy"
                        onSearch={(url) =>
                          url.trim()
                            ? void slotPhoto(index, () =>
                                api<VideoDetail>(`/title-motion/${scene.id}/slots/${index}/photo-link`, "POST", {
                                  url,
                                }),
                              )
                            : undefined
                        }
                      />
                    </Flex>
                  }
                >
                  <Button size="small" type="link" disabled={off}>
                    Ảnh
                  </Button>
                </Popover>
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
