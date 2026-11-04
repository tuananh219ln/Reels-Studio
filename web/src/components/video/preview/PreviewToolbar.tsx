"use client";

import {
  DeleteOutlined,
  PictureOutlined,
  PlusOutlined,
  RedoOutlined,
  SwapOutlined,
  UndoOutlined,
} from "@ant-design/icons";
import { Button, Flex, Popconfirm, Popover, Segmented, Tooltip } from "antd";
import { useRef } from "react";
import type { VideoOptions } from "@/lib/api";

const TRANSITIONS = [
  { value: "fade", label: "Mờ dần" },
  { value: "cut", label: "Cắt thẳng" },
  { value: "slide", label: "Trượt" },
];

/**
 * The small bar beside the phone while the preview stands still: undo and redo what was changed here, a new photo or
 * clip for the scene, the video's transition, a new scene after this one, and removing it (asked first).
 */
export default function PreviewToolbar({
  editable,
  isTitle,
  canUndo,
  canRedo,
  undoLabel,
  redoLabel,
  transition,
  onUndo,
  onRedo,
  onMedia,
  onTransition,
  onAddAfter,
  onDelete,
}: {
  editable: boolean;
  isTitle: boolean;
  canUndo: boolean;
  canRedo: boolean;
  undoLabel: string | null;
  redoLabel: string | null;
  transition: VideoOptions["transition"];
  onUndo: () => void;
  onRedo: () => void;
  onMedia: (file: File) => void;
  onTransition: (transition: VideoOptions["transition"]) => void;
  onAddAfter: () => void;
  onDelete: () => void;
}) {
  const file = useRef<HTMLInputElement>(null);
  const button = (title: string, icon: React.ReactNode, onClick: () => void, disabled = false) => (
    <Tooltip title={title} placement="left">
      <Button aria-label={title} icon={icon} onClick={onClick} disabled={disabled || !editable} />
    </Tooltip>
  );
  return (
    <Flex vertical gap={6} data-testid="preview-toolbar">
      {button(undoLabel ? `Hoàn tác: ${undoLabel} (Ctrl+Z)` : "Hoàn tác (Ctrl+Z)", <UndoOutlined />, onUndo, !canUndo)}
      {button(
        redoLabel ? `Làm lại: ${redoLabel} (Ctrl+Shift+Z)` : "Làm lại (Ctrl+Shift+Z)",
        <RedoOutlined />,
        onRedo,
        !canRedo,
      )}
      <Tooltip title="Đổi ảnh/video của cảnh" placement="left">
        <Button
          aria-label="Đổi ảnh/video của cảnh"
          icon={<PictureOutlined />}
          disabled={!editable}
          onClick={() => file.current?.click()}
        />
      </Tooltip>
      <input
        ref={file}
        type="file"
        accept="image/*,video/*"
        hidden
        aria-label="Ảnh hoặc video mới cho cảnh"
        onChange={(event) => {
          const picked = event.target.files?.[0];
          event.target.value = "";
          if (picked) onMedia(picked);
        }}
      />
      <Popover
        trigger="click"
        placement="left"
        title="Chuyển cảnh (cả video)"
        content={
          <Segmented
            aria-label="Chuyển cảnh"
            value={transition}
            onChange={(value) => onTransition(value as VideoOptions["transition"])}
            options={TRANSITIONS}
          />
        }
      >
        <Tooltip title="Chuyển cảnh" placement="left">
          <Button aria-label="Chuyển cảnh" icon={<SwapOutlined />} disabled={!editable} />
        </Tooltip>
      </Popover>
      {button("Thêm cảnh sau cảnh này", <PlusOutlined />, onAddAfter)}
      <Popconfirm
        title="Xoá cảnh này?"
        description="Không hoàn tác được."
        okText="Xoá"
        cancelText="Huỷ"
        okButtonProps={{ danger: true }}
        onConfirm={onDelete}
        disabled={!editable || isTitle}
      >
        <Tooltip title={isTitle ? "Cảnh tiêu đề không xoá được" : "Xoá cảnh"} placement="left">
          <Button aria-label="Xoá cảnh" danger icon={<DeleteOutlined />} disabled={!editable || isTitle} />
        </Tooltip>
      </Popconfirm>
    </Flex>
  );
}
