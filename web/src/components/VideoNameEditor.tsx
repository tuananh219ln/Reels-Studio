"use client";

import { api, errorMessage, type VideoDetail } from "@/lib/api";
import { CheckOutlined, CloseOutlined, EditOutlined } from "@ant-design/icons";
import { App, Button, Flex, Input, Tooltip, Typography } from "antd";
import Link from "next/link";
import { useState } from "react";

/** The ends of a name that "Nhân bản" piled up: "(copy)", "(bản 2)", "(xáo 3)" (the api's videos.base_name). */
const SUFFIX = /(\s*\((?:copy|bản \d+|xáo \d+)\))+\s*$/i;
export const baseName = (value?: string | null) => (value ?? "").replace(SUFFIX, "").trim();

const MAX_LENGTH = 200;

/** A video's name in the app ("Tên video", not the title scene's text), with a pencil to rename it in place. Saving
 * only changes the name: the video and its MP4 stay as they are. An empty name shows the title again. `editing` and
 * `onEditingChange` let a list keep one row open at a time and open it from the row's menu. */
export default function VideoNameEditor({
  videoId,
  name,
  title,
  href,
  alwaysShowButton,
  editing,
  onEditingChange,
  onSaved,
  maxWidth = 520,
  large,
}: {
  videoId: number;
  name: string | null;
  title: string;
  /** Makes the shown name a link to the video (the lists); the editor's own clicks never follow it. */
  href?: string;
  alwaysShowButton?: boolean;
  editing?: boolean;
  onEditingChange?: (editing: boolean) => void;
  onSaved?: (video: VideoDetail) => void | Promise<void>;
  maxWidth?: number;
  large?: boolean;
}) {
  const { message } = App.useApp();
  const [ownEditing, setOwnEditing] = useState(false);
  const open = editing ?? ownEditing;
  const setOpen = (next: boolean) => (onEditingChange ? onEditingChange(next) : setOwnEditing(next));
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  // What was just saved, shown at once until the parent sends the saved video; `undefined`: nothing pending.
  const [pending, setPending] = useState<string | null | undefined>(undefined);
  const shown = (pending === undefined ? name : pending) || title;

  // The box opens on the current name; synced while rendering so it needs no effect.
  const [wasOpen, setWasOpen] = useState(false);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) setValue(shown);
  }

  async function save() {
    const next = value.trim();
    if (next.length > MAX_LENGTH) {
      message.error(`Tên video tối đa ${MAX_LENGTH} ký tự`);
      return;
    }
    setSaving(true);
    setPending(next || null);
    setOpen(false);
    try {
      const video = await api<VideoDetail>(`/videos/${videoId}`, "PATCH", { name: next || null });
      await onSaved?.(video);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setPending(undefined);
      setSaving(false);
    }
  }

  // A click or key here belongs to the editor, not to the row or card that opens the video.
  const own = {
    onClick: (event: React.SyntheticEvent) => event.stopPropagation(),
    onKeyDown: (event: React.KeyboardEvent) => event.stopPropagation(),
  };

  if (open) {
    const bare = baseName(value);
    return (
      <Flex vertical gap={4} style={{ minWidth: 0, maxWidth: `min(${maxWidth}px, 100%)` }} {...own}>
        <Flex gap={4} wrap="wrap">
          <Input
            autoFocus
            aria-label="Tên video"
            value={value}
            maxLength={MAX_LENGTH}
            disabled={saving}
            onChange={(event) => setValue(event.target.value)}
            onFocus={(event) => event.target.select()}
            onPressEnter={() => void save()}
            onKeyDown={(event) => {
              event.stopPropagation();
              if (event.key === "Escape") setOpen(false);
            }}
            style={{ flex: "1 1 200px", minWidth: 0 }}
          />
          <Button type="primary" icon={<CheckOutlined />} loading={saving} onClick={() => void save()}>
            Lưu
          </Button>
          <Button icon={<CloseOutlined />} disabled={saving} onClick={() => setOpen(false)}>
            Hủy
          </Button>
          {bare !== value.trim() && (
            <Button disabled={saving} onClick={() => setValue(bare)}>
              Bỏ (copy)
            </Button>
          )}
        </Flex>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Tên nội bộ, không ảnh hưởng video đã render.
        </Typography.Text>
      </Flex>
    );
  }

  const text = (
    <Typography.Paragraph
      strong
      ellipsis={{ rows: 2, tooltip: shown }}
      style={{ margin: 0, minWidth: 0, maxWidth: `min(${maxWidth}px, 100%)`, ...(large ? { fontSize: 20 } : {}) }}
      data-testid={href ? undefined : "video-title"}
    >
      {shown}
    </Typography.Paragraph>
  );
  return (
    <Flex align="center" gap={4} className="name-edit-host" style={{ minWidth: 0 }}>
      {href ? (
        <Link prefetch={false} href={href} onClick={(event) => event.stopPropagation()} style={{ minWidth: 0 }}>
          {text}
        </Link>
      ) : (
        text
      )}
      <span {...own} style={{ flex: "none" }}>
        <Tooltip title="Đổi tên">
          <Button
            type="text"
            size="small"
            icon={<EditOutlined />}
            aria-label="Đổi tên video"
            className={alwaysShowButton ? "name-edit-btn always" : "name-edit-btn"}
            onClick={() => setOpen(true)}
          />
        </Tooltip>
      </span>
    </Flex>
  );
}
