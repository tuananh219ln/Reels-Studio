"use client";

import { CommentOutlined, DeleteOutlined, RobotOutlined } from "@ant-design/icons";
import { Button, Flex, Input, Popconfirm, Typography } from "antd";
import { useState } from "react";
import type { VideoNote } from "@/lib/api";
import StatusText from "@/components/StatusText";
import { useMe } from "@/components/MeContext";
import { clockLabel } from "./PreviewTimeline";

const STATUS: Record<VideoNote["status"], { tone: "warning" | "success" | "danger"; label: string }> = {
  open: { tone: "warning", label: "Chưa gửi" },
  sent: { tone: "warning", label: "Chờ AI sửa" },
  done: { tone: "success", label: "Đã sửa" },
};

/**
 * The box under the timeline: a comment typed there is kept at the playhead's second (Enter), for a teammate or for
 * "Nhờ AI sửa" later. Typing pauses nothing; the second is read when Enter is pressed.
 */
export function NoteBar({
  position,
  disabled,
  onAdd,
}: {
  /** Where the preview is, in seconds from the video's start. */
  position: () => number;
  disabled: boolean;
  onAdd: (at: number, text: string) => Promise<boolean>;
}) {
  const [text, setText] = useState("");
  const [at, setAt] = useState(0);
  return (
    <Input
      aria-label="Góp ý tại đầu phát"
      prefix={<CommentOutlined />}
      placeholder={`Góp ý tại ${clockLabel(at, true)}: gõ rồi Enter, để người khác hoặc AI sửa…`}
      value={text}
      disabled={disabled}
      maxLength={500}
      onFocus={() => setAt(position())}
      onChange={(event) => setText(event.target.value)}
      onKeyDown={(event) => event.stopPropagation()}
      onPressEnter={async () => {
        if (!text.trim()) return;
        if (await onAdd(position(), text)) setText("");
      }}
    />
  );
}

/**
 * "Góp ý" in the tools column: every note in the order of the video, its second (a click goes there), who wrote it,
 * whether it is waiting, with the AI or answered (and the answer); and "Nhờ AI sửa", which sends the open notes to
 * one AI job that changes the scenes they point at.
 */
export function NoteTools({
  notes,
  busy,
  canSend,
  onSeek,
  onRemove,
  onSend,
}: {
  notes: VideoNote[];
  /** A job is running on the video (the AI may be on these notes). */
  busy: boolean;
  /** The page is in edit mode and no job runs. */
  canSend: boolean;
  onSeek: (at: number) => void;
  onRemove: (note: VideoNote) => void;
  onSend: () => void;
}) {
  // Only whoever wrote a note deletes it.
  const { me } = useMe();
  const open = notes.filter((note) => note.status === "open").length;
  return (
    <Flex vertical gap={10} data-testid="note-tools">
      <Typography.Text strong>Góp ý</Typography.Text>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Gõ góp ý vào ô dưới thanh thời gian, tại giây cần sửa. “Nhờ AI sửa” gửi mọi góp ý chưa gửi cho AI: AI sửa chữ,
        lời đọc của cảnh đó hoặc thêm lớp chữ, rồi trả lời từng góp ý.
      </Typography.Text>
      <Popconfirm
        title={`Gửi ${open} góp ý cho AI sửa?`}
        description="Tốn một lượt gọi AI. Video khoá lại cho tới khi AI sửa xong."
        okText="Gửi"
        cancelText="Huỷ"
        disabled={!canSend || open === 0}
        onConfirm={onSend}
      >
        <Button type="primary" icon={<RobotOutlined />} disabled={!canSend || open === 0} loading={busy && !canSend}>
          Nhờ AI sửa{open > 0 ? ` (${open} góp ý)` : ""}
        </Button>
      </Popconfirm>
      {notes.length === 0 ? (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Chưa có góp ý nào.
        </Typography.Text>
      ) : (
        <Flex vertical gap={6} role="list" aria-label="Các góp ý">
          {notes.map((note) => (
            <Flex
              key={note.id}
              vertical
              gap={2}
              role="listitem"
              data-testid="note"
              style={{ border: "1px solid #e7e8ea", borderRadius: 6, padding: "6px 8px" }}
            >
              <Flex align="center" gap={6}>
                <Button
                  size="small"
                  type="link"
                  style={{ padding: 0, fontVariantNumeric: "tabular-nums" }}
                  onClick={() => onSeek(note.at)}
                >
                  {clockLabel(note.at, true)}
                </Button>
                <StatusText tone={STATUS[note.status].tone}>{STATUS[note.status].label}</StatusText>
                <Typography.Text type="secondary" ellipsis style={{ flex: 1, minWidth: 0, fontSize: 12 }}>
                  {note.created_by}
                </Typography.Text>
                {note.created_by_id === me.id && (
                  <Popconfirm
                    title="Xoá góp ý này?"
                    okText="Xoá"
                    cancelText="Huỷ"
                    okButtonProps={{ danger: true }}
                    disabled={note.status === "sent"}
                    onConfirm={() => onRemove(note)}
                  >
                    <Button
                      size="small"
                      type="text"
                      danger
                      aria-label="Xoá góp ý"
                      icon={<DeleteOutlined />}
                      disabled={note.status === "sent"}
                    />
                  </Popconfirm>
                )}
              </Flex>
              <Typography.Text style={{ fontSize: 13 }}>{note.text}</Typography.Text>
              {note.reply && (
                <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="note-reply">
                  ↳ {note.reply}
                </Typography.Text>
              )}
            </Flex>
          ))}
        </Flex>
      )}
    </Flex>
  );
}
