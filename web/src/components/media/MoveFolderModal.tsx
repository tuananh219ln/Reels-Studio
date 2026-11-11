"use client";

import { App, Form, Modal, Typography } from "antd";
import { useState } from "react";
import FolderSelect from "@/components/media/FolderSelect";
import { api, errorMessage, type MediaFolder } from "@/lib/api";

type Props = {
  ids: number[];
  /** The one item's folder, preselected; undefined for a batch. */
  current?: string;
  folders: MediaFolder[];
  onClose: () => void;
  onMoved: (folder: string, folders: MediaFolder[]) => void;
};

/**
 * "Chuyển thư mục" for one item or a chosen batch: only their folder label changes, never their id or file, so what
 * points at them (a scene, the assistant over MCP) still holds. `ids` empty: closed.
 */
export default function MoveFolderModal(props: Props) {
  // Mounted afresh each time it opens, so it starts on the item's own folder.
  return props.ids.length > 0 ? <MoveDialog {...props} /> : null;
}

function MoveDialog({ ids, current, folders, onClose, onMoved }: Props) {
  const { message } = App.useApp();
  const [target, setTarget] = useState<string | null>(current ?? null);
  const [busy, setBusy] = useState(false);

  async function move() {
    if (target === null) return;
    setBusy(true);
    try {
      const result = await api<{ moved: number; folders: MediaFolder[] }>("/media/move", "POST", {
        ids,
        folder: target,
      });
      message.success(`Đã chuyển ${result.moved} tư liệu ${target ? `vào “${target}”` : "ra Không thư mục"}`);
      onMoved(target, result.folders);
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
      title={ids.length > 1 ? `Chuyển ${ids.length} tư liệu sang thư mục khác` : "Chuyển thư mục"}
      okText="Chuyển thư mục"
      cancelText="Huỷ"
      okButtonProps={{ disabled: target === null || (current !== undefined && target === current), loading: busy }}
      onOk={move}
      onCancel={onClose}
      destroyOnHidden
    >
      <Form layout="vertical">
        <Form.Item label="Thư mục" style={{ marginBottom: 8 }}>
          <FolderSelect
            aria-label="Thư mục chuyển tới"
            folders={folders}
            value={target}
            onChange={setTarget}
            allowNone
            style={{ width: "100%" }}
          />
        </Form.Item>
      </Form>
      <Typography.Text type="secondary">
        Tư liệu giữ nguyên mã và file; cảnh và trợ lý đang dùng nó không bị ảnh hưởng.
      </Typography.Text>
    </Modal>
  );
}
