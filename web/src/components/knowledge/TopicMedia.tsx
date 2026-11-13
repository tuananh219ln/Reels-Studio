"use client";
import MediaLibrary from "@/components/media/MediaLibrary";

import EmptyState from "@/components/EmptyState";
import FolderSelect from "@/components/media/FolderSelect";
import { api, errorMessage, type KnowledgeTopic, type MediaFolder, type MediaList } from "@/lib/api";
import {
  DisconnectOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  LinkOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { App, Button, Flex, Form, Modal, Popconfirm, Spin, Tag, Tooltip, Typography } from "antd";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type Update = (body: Partial<KnowledgeTopic>) => Promise<KnowledgeTopic>;

/**
 * "Tư liệu" of a topic group: the team's one "Kho tư liệu" filtered on the folder the group links (with its
 * subfolders), uploads into that folder, and a link to the full library on the same filter. Not a library of its own:
 * a photo two groups use sits once in the library (docs/decisions/2026-11-11-media-folders.md). Linking a folder is
 * an edit of the group (`locked`: "Cho cả đội sửa" is off and the group is not the member's).
 */
export default function TopicMedia({
  topic,
  update,
  locked,
}: {
  topic: KnowledgeTopic;
  update: Update;
  locked: boolean;
}) {
  const { message } = App.useApp();
  const folder = topic.media_folder;
  const [data, setData] = useState<MediaList | null>(null);
  const [failed, setFailed] = useState(false);
  const [linking, setLinking] = useState(false);
  const [uploading, setUploading] = useState(false);

  const read = useCallback(
    // Unlinked: only the folders matter, for "Liên kết thư mục".
    async () => {
      const found = await api<MediaList>(folder ? `/media?folder=${encodeURIComponent(folder)}` : "/media");
      return folder ? found : { items: [], folders: found.folders, tags: found.tags };
    },
    [folder],
  );

  const load = useCallback(async () => {
    try {
      setData(await read());
      setFailed(false);
    } catch (err) {
      setFailed(true);
      message.error(errorMessage(err));
    }
  }, [read, message]);

  useEffect(() => {
    let open = true;
    read().then(
      (found) => {
        if (!open) return;
        setData(found);
        setFailed(false);
      },
      (err) => {
        if (!open) return;
        setFailed(true);
        message.error(errorMessage(err));
      },
    );
    return () => {
      open = false;
    };
  }, [read, message]);

  async function unlink() {
    try {
      await update({ media_folder: null });
      message.success("Đã bỏ liên kết thư mục; tư liệu vẫn ở trong Kho tư liệu");
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  if (!data) {
    return failed ? (
      <EmptyState description="Không tải được tư liệu của nhóm" action={<Button onClick={load}>Thử lại</Button>} />
    ) : (
      <Flex justify="center" style={{ padding: 32 }}>
        <Spin />
      </Flex>
    );
  }

  const linkDialog = linking && (
    <LinkDialog topic={topic} folders={data.folders} update={update} onClose={() => setLinking(false)} />
  );

  if (!folder) {
    return (
      <>
        <EmptyState
          description="Nhóm chưa liên kết thư mục nào trong Kho tư liệu"
          action={
            <Tooltip title={locked ? "Chỉ người tạo nhóm liên kết được thư mục" : undefined}>
              <Button type="primary" icon={<LinkOutlined />} disabled={locked} onClick={() => setLinking(true)}>
                Liên kết thư mục
              </Button>
            </Tooltip>
          }
        />
        {linkDialog}
      </>
    );
  }

  const count = data.items.length;
  return (
    <Flex vertical gap={12}>
      <Flex gap={8} wrap align="center" justify="space-between">
        <Typography.Text>
          Thư mục{" "}
          <Tag icon={<FolderOutlined />} style={{ marginInlineEnd: 0 }}>
            {folder}
          </Tag>
          , {count} tư liệu
        </Typography.Text>
        <Flex gap={8} wrap>
          <Button
            icon={<UploadOutlined />}
            type={uploading ? "default" : "primary"}
            onClick={() => setUploading((value) => !value)}
          >
            {uploading ? "Đóng tải ảnh" : "Tải ảnh vào thư mục này"}
          </Button>
          <Link href={`/media?folder=${encodeURIComponent(folder)}`}>
            <Button icon={<FolderOpenOutlined />}>Mở trong Kho tư liệu</Button>
          </Link>
          <Button icon={<LinkOutlined />} disabled={locked} onClick={() => setLinking(true)}>
            Đổi thư mục
          </Button>
          <Popconfirm
            title="Bỏ liên kết thư mục?"
            description="Tư liệu vẫn ở trong Kho tư liệu, chỉ không hiện ở nhóm này nữa."
            okText="Bỏ liên kết"
            okButtonProps={{ danger: true }}
            cancelText="Huỷ"
            onConfirm={unlink}
            disabled={locked}
          >
            <Button icon={<DisconnectOutlined />} disabled={locked}>
              Bỏ liên kết
            </Button>
          </Popconfirm>
        </Flex>
      </Flex>
      <MediaLibrary
        key={folder}
        lockedFolder={folder}
        embedded
        keyword={topic.name}
        onChanged={load}
        showUpload={uploading}
      />
      {linkDialog}
    </Flex>
  );
}

/** "Liên kết thư mục": one of the library's folders (one another group links cannot be picked) or a new name. */
function LinkDialog({
  topic,
  folders,
  update,
  onClose,
}: {
  topic: KnowledgeTopic;
  folders: MediaFolder[];
  update: Update;
  onClose: () => void;
}) {
  const { message } = App.useApp();
  const [chosen, setChosen] = useState<string | null>(topic.media_folder);
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!chosen) return;
    setBusy(true);
    try {
      await update({ media_folder: chosen });
      message.success(`Nhóm đã liên kết thư mục “${chosen}”`);
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
      title={`Liên kết thư mục cho nhóm “${topic.name}”`}
      okText="Liên kết thư mục"
      cancelText="Huỷ"
      okButtonProps={{ disabled: !chosen || chosen === topic.media_folder, loading: busy }}
      onOk={save}
      onCancel={onClose}
    >
      <Form layout="vertical">
        <Form.Item label="Thư mục trong Kho tư liệu" style={{ marginBottom: 8 }}>
          <FolderSelect
            aria-label="Thư mục của nhóm"
            folders={folders}
            value={chosen}
            onChange={setChosen}
            forTopic={topic.id}
            style={{ width: "100%" }}
          />
        </Form.Item>
      </Form>
      <Typography.Text type="secondary">
        Tab Tư liệu hiện ảnh của thư mục này (gồm thư mục con) trong kho chung. Mỗi thư mục chỉ thuộc một nhóm.
      </Typography.Text>
    </Modal>
  );
}
