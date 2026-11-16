"use client";

import { App, Button, Flex, Form, Input, InputNumber, Modal, Space, Typography } from "antd";
import { useRef, useState } from "react";
import FolderSelect from "@/components/media/FolderSelect";
import TagSelect from "@/components/media/TagSelect";
import { api, errorMessage, type MediaFolder, type MediaItem, type MediaTag } from "@/lib/api";

const MIN_SECONDS = 1;
const MAX_SECONDS = 60;
const DEFAULT_LENGTH = 5;

const round1 = (value: number) => Math.round(value * 10) / 10;

/**
 * "Cắt thành file mới": a part of a library clip saved as a new item of the library (`POST /media/{id}/cut`), with
 * its folder and tags; the clip itself stays. Null `item`: closed. Mounted afresh each time it opens.
 */
export default function CutClipModal(props: {
  item: MediaItem | null;
  folders: MediaFolder[];
  tags: MediaTag[];
  onClose: () => void;
  onCut: (made: MediaItem) => void;
}) {
  return props.item ? <CutDialog {...props} item={props.item} /> : null;
}

function CutDialog({
  item,
  folders,
  tags,
  onClose,
  onCut,
}: {
  item: MediaItem;
  folders: MediaFolder[];
  tags: MediaTag[];
  onClose: () => void;
  onCut: (made: MediaItem) => void;
}) {
  const { message } = App.useApp();
  const video = useRef<HTMLVideoElement>(null);
  const total = item.seconds ?? MAX_SECONDS;
  const [start, setStart] = useState(0);
  const [length, setLength] = useState(Math.min(DEFAULT_LENGTH, total));
  const [folder, setFolder] = useState<string | null>(item.folder);
  const [chosen, setChosen] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const end = round1(start + length);
  const tooLong = end > total + 0.05;
  const ready = chosen.length > 0 && folder !== null && !tooLong && length >= MIN_SECONDS;

  function fromPlayer() {
    const at = video.current?.currentTime;
    if (at !== undefined) setStart(round1(Math.min(at, Math.max(0, total - MIN_SECONDS))));
  }

  async function cut() {
    setBusy(true);
    try {
      const made = await api<MediaItem>(`/media/${item.id}/cut`, "POST", {
        start,
        length,
        folder: folder ?? "",
        tags: chosen,
        name: name.trim() || null,
      });
      message.success(`Đã lưu “${made.name}” vào kho`);
      onCut(made);
      onClose();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      title={`Cắt “${item.name}” thành file mới`}
      okText="Cắt và lưu vào kho"
      cancelText="Huỷ"
      okButtonProps={{ disabled: !ready, loading: busy }}
      onOk={cut}
      onCancel={onClose}
      destroyOnHidden
    >
      <Flex vertical gap={12}>
        <div style={{ background: "#000", borderRadius: 8, overflow: "hidden", textAlign: "center" }}>
          <video
            ref={video}
            src={item.file_url}
            poster={item.thumb_url}
            controls
            preload="metadata"
            aria-label="Clip gốc"
            style={{ maxWidth: "100%", maxHeight: "40vh" }}
          />
        </div>
        <Form layout="vertical" requiredMark={false}>
          <Space wrap align="end" size={12}>
            <Form.Item label="Bắt đầu (giây)" style={{ marginBottom: 8 }}>
              <InputNumber
                aria-label="Giây bắt đầu"
                min={0}
                max={Math.max(0, total - MIN_SECONDS)}
                step={0.1}
                value={start}
                onChange={(value) => setStart(value ?? 0)}
              />
            </Form.Item>
            <Form.Item label="Độ dài (giây)" style={{ marginBottom: 8 }}>
              <InputNumber
                aria-label="Độ dài đoạn cắt"
                min={MIN_SECONDS}
                max={MAX_SECONDS}
                step={0.5}
                value={length}
                onChange={(value) => setLength(value ?? MIN_SECONDS)}
              />
            </Form.Item>
            <Form.Item style={{ marginBottom: 8 }}>
              <Button onClick={fromPlayer}>Lấy giây đang xem</Button>
            </Form.Item>
          </Space>
          <Typography.Paragraph type={tooLong ? "danger" : "secondary"} style={{ marginTop: 0 }}>
            {tooLong
              ? `Đoạn ${start}–${end} giây vượt quá độ dài clip (${total} giây)`
              : `Lấy đoạn ${start}–${end} giây của clip dài ${total} giây, không có tiếng.`}
          </Typography.Paragraph>
          <Form.Item label="Thư mục" style={{ marginBottom: 8 }}>
            <FolderSelect
              aria-label="Thư mục của đoạn cắt"
              folders={folders}
              value={folder}
              onChange={setFolder}
              allowNone
              style={{ width: "100%" }}
            />
          </Form.Item>
          <Form.Item label="Thẻ (bắt buộc: video, cảnh, món hoặc chủ đề)" style={{ marginBottom: 8 }}>
            <TagSelect
              aria-label="Thẻ của đoạn cắt"
              tags={tags}
              value={chosen}
              onChange={setChosen}
              placeholder="Ví dụ 189-canh1-trung-la-dinh-lang"
              style={{ width: "100%" }}
            />
          </Form.Item>
          <Form.Item label="Tên (để trống: tên clip kèm đoạn cắt)" style={{ marginBottom: 8 }}>
            <Input
              aria-label="Tên đoạn cắt"
              maxLength={200}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Form.Item>
        </Form>
        <Typography.Text type="secondary">Clip gốc vẫn giữ trong kho; xoá riêng khi không cần nữa.</Typography.Text>
      </Flex>
    </Modal>
  );
}
