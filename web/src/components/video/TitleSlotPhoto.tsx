"use client";

import { COLORS } from "@/app/theme";
import { DownOutlined, GoogleOutlined, InboxOutlined, PictureOutlined, SnippetsOutlined } from "@ant-design/icons";
import { App, Badge, Button, Dropdown, Flex, Input, Popover, Tooltip, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { api, type SceneData, type VideoDetail } from "@/lib/api";
import { linkFromTransfer, googleImagesUrl } from "@/lib/mediaLinks";
import { setGoogleCellTarget } from "@/lib/googleExtension";
import MediaLibraryPicker from "./MediaLibraryPicker";

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_KEYWORDS = 6;

/**
 * What to search Google Ảnh for to fill one slot of the title: its name, the name with the video's main keyword, then
 * the keywords of the scene it takes its photo from (the one told to, else the one in the same place below the
 * title), and that scene's English one. Lower case, no repeats, at most six.
 */
export function slotKeywords(
  title: SceneData,
  index: number,
  name: string,
  scenes: SceneData[],
  from: number | null,
): string[] {
  const listed = scenes.filter((scene) => !scene.is_title);
  const source = (from ? scenes.find((scene) => scene.id === from) : null) ?? listed[index] ?? null;
  const lower = name.trim().toLowerCase();
  const topic = title.keywords[0]?.trim().toLowerCase() ?? "";
  const found = [
    lower,
    lower && topic && !lower.includes(topic) ? `${lower} ${topic}` : "",
    ...(source?.keywords ?? []).slice(0, 2),
    source?.keywords_en[0] ?? "",
  ];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const word of found.map((item) => item.trim())) {
    if (word && !seen.has(word.toLowerCase())) {
      seen.add(word.toLowerCase());
      out.push(word);
    }
  }
  return out.slice(0, MAX_KEYWORDS);
}

/**
 * "Ảnh ▾" of one slot of the title and the small picture before its name: a popover with the same ways to get a photo
 * as a scene has (upload, paste, the library, Google), each putting the photo in this slot. What is picked is saved by
 * `TitleMotionField`; the slot shows it from the next "Dựng lại tiêu đề".
 */
export default function TitleSlotPhoto({
  title,
  index,
  name,
  photoUrl,
  from,
  disabled,
  onFile,
  onLink,
  onLibrary,
  onRemove,
}: {
  title: SceneData;
  index: number;
  /** The slot's name as it is in the box now. */
  name: string;
  photoUrl: string | null;
  from: number | null;
  disabled: boolean;
  onFile: (file: File) => void;
  onLink: (text: string) => void;
  onLibrary: (mediaId: number) => Promise<VideoDetail>;
  onRemove: () => void;
}) {
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [library, setLibrary] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [scenes, setScenes] = useState<SceneData[] | null>(null);
  const [other, setOther] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const latest = useRef({ onFile, onLink });
  useEffect(() => {
    latest.current = { onFile, onLink };
  });

  // The scenes' keywords, read when the popover opens so they are the ones saved now.
  useEffect(() => {
    if (!open) {
      return;
    }
    let live = true;
    api<VideoDetail>(`/videos/${title.video_id}`)
      .then((video) => live && setScenes(video.scenes))
      .catch(() => live && setScenes([]));
    return () => {
      live = false;
    };
  }, [open, title.video_id]);

  /** A copied photo or a photo's link: from the clipboard, or from a Ctrl/Cmd+V while the popover is open. */
  function fromData(data: DataTransfer): boolean {
    const file = Array.from(data.files).find((item) => item.type.startsWith("image/"));
    if (file) {
      latest.current.onFile(file);
      return true;
    }
    const text = data.getData("text/plain").trim();
    if (/^(https?:\/\/\S+|data:image\/)/i.test(text)) {
      latest.current.onLink(text);
      return true;
    }
    return false;
  }

  useEffect(() => {
    if (!open || disabled) {
      return;
    }
    const listen = (event: ClipboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, [contenteditable=true]") || !event.clipboardData) {
        return;
      }
      if (fromData(event.clipboardData)) {
        event.preventDefault();
      } else {
        void message.error("Chưa có ảnh hoặc link ảnh trong clipboard");
      }
    };
    document.addEventListener("paste", listen);
    return () => document.removeEventListener("paste", listen);
  }, [open, disabled, message]);

  async function pasteFromClipboard() {
    try {
      for (const item of await navigator.clipboard.read()) {
        const type = item.types.find((kind) => IMAGE_TYPES.includes(kind));
        if (type) {
          const blob = await item.getType(type);
          onFile(new File([blob], `anh-dan.${type.split("/")[1].replace("jpeg", "jpg")}`, { type }));
          return;
        }
        if (item.types.includes("text/plain")) {
          const text = (await (await item.getType("text/plain")).text()).trim();
          if (/^(https?:\/\/\S+|data:image\/)/i.test(text)) {
            onLink(text);
            return;
          }
        }
      }
    } catch {
      // No permission to read the clipboard: Ctrl/Cmd+V in the popover does the same.
      void message.info("Trình duyệt chưa cho đọc clipboard: bấm Ctrl+V (hoặc Cmd+V) khi đang mở hộp này");
      return;
    }
    void message.error("Chưa có ảnh hoặc link ảnh trong clipboard");
  }

  function drop(event: React.DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (disabled) {
      return;
    }
    const file = event.dataTransfer.files[0];
    if (file) {
      onFile(file);
      return;
    }
    const link = linkFromTransfer(event.dataTransfer);
    if (link) {
      onLink(link);
    } else {
      void message.error("Không nhận ra ảnh vừa thả: hãy kéo chính tấm ảnh, hoặc sao chép ảnh rồi dán");
    }
  }

  function search(keyword: string) {
    const word = keyword.trim();
    if (!word) {
      return;
    }
    // The popover stays open, and the Chrome extension's photos go to this slot for the next ten minutes.
    setGoogleCellTarget(title.id, index, `Ô ${index + 1}: ${name.trim() || "chưa có tên"}`);
    window.open(googleImagesUrl(word), "_blank", "noopener");
  }

  const keywords = scenes ? slotKeywords(title, index, name, scenes, from) : [];
  const label = `Ảnh cho ô ${index + 1}${name.trim() ? `: ${name.trim()}` : ""}`;

  const content = (
    <Flex
      vertical
      gap={8}
      style={{
        width: 280,
        outline: dragging ? `2px dashed ${COLORS.primary}` : undefined,
        outlineOffset: 4,
      }}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(!disabled);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={drop}
      data-testid={`title-slot-picker-${index}`}
    >
      <Flex gap={8}>
        <Button icon={<InboxOutlined />} disabled={disabled} style={{ flex: 1 }} onClick={() => input.current?.click()}>
          Tải lên
        </Button>
        <Tooltip title="Dán ảnh hoặc link ảnh đã sao chép (Ctrl/Cmd+V cũng được)">
          <Button
            icon={<SnippetsOutlined />}
            disabled={disabled}
            style={{ flex: 1 }}
            onClick={() => void pasteFromClipboard()}
          >
            Dán
          </Button>
        </Tooltip>
      </Flex>
      <input
        ref={input}
        type="file"
        accept="image/*"
        hidden
        aria-label={`Tải ảnh cho ô ${index + 1}`}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) {
            onFile(file);
          }
        }}
      />
      <Button
        icon={<PictureOutlined />}
        disabled={disabled}
        block
        style={{ textAlign: "left" }}
        onClick={() => setLibrary(true)}
      >
        Chọn từ kho <DownOutlined style={{ fontSize: 10, float: "right", marginTop: 5 }} />
      </Button>
      <Tooltip title="Mở Google Ảnh (ảnh dọc) với từ khóa bạn chọn; sao chép ảnh ưng ý rồi quay lại dán vào đây (có tiện ích Chrome của nhóm thì chuột phải vào ảnh, chọn “Gửi ảnh vào Reels Studio”)">
        <Dropdown
          trigger={["click"]}
          disabled={disabled}
          getPopupContainer={(node) => node.parentElement ?? document.body}
          menu={{
            items: [
              { key: "head", type: "group", label: "Tìm trên Google với từ khóa:" },
              ...keywords.map((word) => ({ key: `k:${word}`, label: word })),
              {
                key: "other",
                label: (
                  <Input
                    size="small"
                    placeholder="Từ khóa khác…"
                    value={other}
                    onChange={(event) => setOther(event.target.value)}
                    onClick={(event) => event.stopPropagation()}
                    onKeyDown={(event) => {
                      event.stopPropagation();
                      if (event.key === "Enter") {
                        search(other);
                      }
                    }}
                  />
                ),
              },
            ],
            onClick: ({ key }) => {
              if (key.startsWith("k:")) {
                search(key.slice(2));
              }
            },
          }}
        >
          <Button icon={<GoogleOutlined />} disabled={disabled} block style={{ textAlign: "left" }}>
            Google <DownOutlined style={{ fontSize: 10, float: "right", marginTop: 5 }} />
          </Button>
        </Dropdown>
      </Tooltip>
      {photoUrl && (
        <Flex align="center" gap={10}>
          {/* eslint-disable-next-line @next/next/no-img-element -- a photo the api serves, sized by the box */}
          <img
            src={photoUrl}
            alt={`Ảnh hiện tại của ô ${index + 1}`}
            width={64}
            height={64}
            style={{ objectFit: "cover", borderRadius: 6 }}
          />
          <Button type="link" size="small" danger disabled={disabled} onClick={onRemove}>
            Xóa ảnh
          </Button>
        </Flex>
      )}
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Ảnh mới hiện trong tiêu đề sau khi bấm “Dựng lại tiêu đề”.
      </Typography.Text>
    </Flex>
  );

  return (
    <>
      <button
        type="button"
        aria-label={`Ảnh của ô ${index + 1}`}
        title={photoUrl ? "Ô có ảnh riêng" : "Ô lấy ảnh từ cảnh tương ứng"}
        data-testid={`title-slot-thumb-${index}`}
        tabIndex={-1}
        onClick={() => setOpen(true)}
        onDragOver={(event) => event.preventDefault()}
        onDrop={drop}
        style={{
          order: -1,
          flex: "0 0 32px",
          width: 32,
          height: 32,
          padding: 0,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 6,
          overflow: "hidden",
          background: COLORS.muted,
          color: COLORS.primary,
          fontWeight: 700,
          cursor: "pointer",
        }}
      >
        {photoUrl ? (
          // eslint-disable-next-line @next/next/no-img-element -- a photo the api serves, sized by the box
          <img src={photoUrl} alt="" width={32} height={32} style={{ objectFit: "cover", display: "block" }} />
        ) : (
          "?"
        )}
      </button>
      <Popover
        trigger="click"
        placement="bottomLeft"
        open={open}
        onOpenChange={setOpen}
        title={
          <Flex justify="space-between" align="center" gap={8}>
            <span>{label}</span>
            <Button type="text" size="small" aria-label="Đóng" onClick={() => setOpen(false)}>
              ✕
            </Button>
          </Flex>
        }
        content={content}
      >
        <Badge dot={!photoUrl} color={COLORS.brand} offset={[-4, 4]}>
          <Button size="small" disabled={disabled} aria-label={`Ảnh cho ô ${index + 1}`}>
            Ảnh <DownOutlined style={{ fontSize: 10 }} />
          </Button>
        </Badge>
      </Popover>
      {library && (
        <MediaLibraryPicker
          videoId={title.video_id}
          hasPicture={false}
          usedFor="ô tiêu đề"
          onUse={async (mediaId) => {
            const saved = await onLibrary(mediaId);
            setOpen(false);
            return saved;
          }}
          onClose={() => setLibrary(false)}
        />
      )}
    </>
  );
}
