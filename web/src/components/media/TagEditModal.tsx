"use client";

import { App, Form, Modal, Typography } from "antd";
import { useState } from "react";
import TagSelect from "@/components/media/TagSelect";
import { api, errorMessage, type MediaItem, type MediaTag } from "@/lib/api";

/** "Sửa thẻ" of one item (its whole set), or "Thêm thẻ" / "Gỡ thẻ" on the chosen ones. */
export type TagEdit =
  { mode: "set"; item: MediaItem } | { mode: "add"; ids: number[] } | { mode: "remove"; ids: number[] };

const TITLES = { set: "Sửa thẻ", add: "Thêm thẻ", remove: "Gỡ thẻ" } as const;

/** The dialog for a `TagEdit`; null: closed. Mounted afresh each time it opens, so it starts on the item's tags. */
export default function TagEditModal({
  edit,
  tags,
  onClose,
  onSaved,
}: {
  edit: TagEdit | null;
  tags: MediaTag[];
  onClose: () => void;
  onSaved: () => void;
}) {
  return edit ? <TagDialog edit={edit} tags={tags} onClose={onClose} onSaved={onSaved} /> : null;
}

function TagDialog({
  edit,
  tags,
  onClose,
  onSaved,
}: {
  edit: TagEdit;
  tags: MediaTag[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { message } = App.useApp();
  const [chosen, setChosen] = useState<string[]>(edit.mode === "set" ? edit.item.tags : []);
  const [busy, setBusy] = useState(false);
  const count = edit.mode === "set" ? 1 : edit.ids.length;

  async function save() {
    setBusy(true);
    try {
      if (edit.mode === "set") {
        await api<MediaItem>(`/media/${edit.item.id}`, "PATCH", { tags: chosen });
        message.success(`Đã lưu thẻ của “${edit.item.name}”`);
      } else {
        const result = await api<{ changed: number }>("/media/tags", "POST", { ids: edit.ids, [edit.mode]: chosen });
        message.success(`Đã ${edit.mode === "add" ? "thêm" : "gỡ"} thẻ ở ${result.changed} tư liệu`);
      }
      onSaved();
      onClose();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const title = edit.mode === "set" ? `Sửa thẻ “${edit.item.name}”` : `${TITLES[edit.mode]} cho ${count} tư liệu`;
  return (
    <Modal
      open
      title={title}
      okText={TITLES[edit.mode]}
      okButtonProps={{ disabled: edit.mode !== "set" && !chosen.length, loading: busy, danger: edit.mode === "remove" }}
      cancelText="Huỷ"
      onOk={save}
      onCancel={onClose}
    >
      <Form layout="vertical">
        <Form.Item label="Thẻ" style={{ marginBottom: 8 }}>
          <TagSelect
            aria-label="Thẻ của tư liệu"
            tags={tags}
            value={chosen}
            onChange={setChosen}
            allowNew={edit.mode !== "remove"}
            placeholder={edit.mode === "remove" ? "Chọn thẻ cần gỡ…" : "Chọn thẻ có sẵn hoặc gõ thẻ mới…"}
            style={{ width: "100%" }}
          />
        </Form.Item>
      </Form>
      <Typography.Text type="secondary">
        Thẻ được lưu chữ thường, không dấu, nối bằng dấu gạch: “Xoay cổ” thành “xoay-co”. Ưu tiên chọn thẻ có sẵn.
      </Typography.Text>
    </Modal>
  );
}
