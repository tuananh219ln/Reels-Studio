"use client";

import { DeleteOutlined, EditOutlined } from "@ant-design/icons";
import { App, Button, Form, Input, Modal, Typography } from "antd";
import { useState } from "react";
import { cleanFolder } from "@/components/media/FolderSelect";
import { api, errorMessage, type MediaFolder } from "@/lib/api";

/** The folder and its subfolders, as the library's filter shows them. */
function within(folders: MediaFolder[], folder: string): MediaFolder[] {
  return folders.filter((row) => row.folder === folder || row.folder.startsWith(`${folder}/`));
}

/**
 * "Đổi tên thư mục" and "Xoá thư mục" for the folder being shown on /media. Both change only the items' folder label
 * (with the subfolders'): renaming takes a linked group's "Tư liệu" along, deleting puts the items in "Không thư mục"
 * and unlinks the group; no item is ever deleted here.
 */
export default function FolderActions({
  folder,
  folders,
  onRenamed,
  onCleared,
}: {
  folder: string;
  folders: MediaFolder[];
  onRenamed: (to: string, folders: MediaFolder[]) => void;
  onCleared: (folders: MediaFolder[]) => void;
}) {
  const { message, modal } = App.useApp();
  const [renaming, setRenaming] = useState(false);
  const inside = within(folders, folder);
  const count = inside.reduce((sum, row) => sum + row.count, 0);
  const groups = inside.flatMap((row) => (row.topic ? [row.topic] : []));

  function clear() {
    modal.confirm({
      title: `Xoá thư mục “${folder}”?`,
      content: (
        <Typography.Paragraph style={{ marginBottom: 0 }}>
          {count} tư liệu{inside.length > 1 ? " (gồm cả thư mục con)" : ""} chuyển về Không thư mục; không tư liệu nào
          bị xoá.
          {groups.length > 0 && ` Nhóm ${groups.join(", ")} sẽ bỏ liên kết thư mục này ở mục Tư liệu.`}
        </Typography.Paragraph>
      ),
      okText: "Xoá thư mục",
      okButtonProps: { danger: true },
      cancelText: "Huỷ",
      onOk: async () => {
        try {
          const result = await api<{ cleared: number; folders: MediaFolder[] }>("/media/folders/clear", "POST", {
            folder,
          });
          message.success(`Đã xoá thư mục, ${result.cleared} tư liệu về Không thư mục`);
          onCleared(result.folders);
        } catch (err) {
          message.error(errorMessage(err));
        }
      },
    });
  }

  return (
    <>
      <Button icon={<EditOutlined />} onClick={() => setRenaming(true)}>
        Đổi tên thư mục
      </Button>
      <Button danger icon={<DeleteOutlined />} onClick={clear}>
        Xoá thư mục
      </Button>
      {renaming && (
        <RenameDialog
          folder={folder}
          count={count}
          groups={groups}
          onClose={() => setRenaming(false)}
          onRenamed={onRenamed}
        />
      )}
    </>
  );
}

function RenameDialog({
  folder,
  count,
  groups,
  onClose,
  onRenamed,
}: {
  folder: string;
  count: number;
  groups: string[];
  onClose: () => void;
  onRenamed: (to: string, folders: MediaFolder[]) => void;
}) {
  const { message } = App.useApp();
  const [name, setName] = useState(folder);
  const [busy, setBusy] = useState(false);
  const to = cleanFolder(name);

  async function rename() {
    setBusy(true);
    try {
      const result = await api<{ moved: number; folders: MediaFolder[] }>("/media/folders/rename", "POST", {
        folder,
        to,
      });
      message.success(`Đã đổi tên thư mục thành “${to}”`);
      onRenamed(to, result.folders);
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
      title={`Đổi tên thư mục “${folder}”`}
      okText="Đổi tên thư mục"
      cancelText="Huỷ"
      okButtonProps={{ disabled: !to || to === folder, loading: busy }}
      onOk={rename}
      onCancel={onClose}
    >
      <Form layout="vertical" onFinish={rename}>
        <Form.Item label="Tên mới" htmlFor="media-folder-rename" style={{ marginBottom: 8 }}>
          <Input
            id="media-folder-rename"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={200}
            autoFocus
          />
        </Form.Item>
      </Form>
      <Typography.Text type="secondary">
        {count} tư liệu đổi theo, giữ nguyên mã và file. Trùng tên thư mục đã có thì gộp vào đó.
        {groups.length > 0 && ` Nhóm ${groups.join(", ")} vẫn liên kết với thư mục sau khi đổi tên.`}
      </Typography.Text>
    </Modal>
  );
}
