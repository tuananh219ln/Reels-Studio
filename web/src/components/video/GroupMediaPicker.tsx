"use client";

import { SearchOutlined } from "@ant-design/icons";
import { App, Button, Empty, Flex, Input, Modal, Spin, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { api, errorMessage, type GroupMedia, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

/**
 * "Đã dùng trong nhóm": the photos and clips the other videos of this scene's topic group use, best match for the
 * scene's keywords first, or for the words typed. "Dùng" copies one into the scene, so a picture chosen with care for
 * one video serves the next without searching again.
 */
export default function GroupMediaPicker({
  sceneId,
  hasPicture,
  onClose,
}: {
  sceneId: number;
  hasPicture: boolean;
  onClose: () => void;
}) {
  const { message, modal } = App.useApp();
  const editor = useEditor();
  const [query, setQuery] = useState("");
  const [data, setData] = useState<GroupMedia | null>(null);
  const [using, setUsing] = useState<number | null>(null);

  useEffect(() => {
    let live = true;
    // A short wait while typing, so each word does not send its own search.
    const timer = setTimeout(async () => {
      try {
        const params = new URLSearchParams(query.trim() ? { q: query.trim() } : {});
        const found = await api<GroupMedia>(`/scenes/${sceneId}/group-media?${params.toString()}`);
        if (live) setData(found);
      } catch (err) {
        if (live) message.error(errorMessage(err));
      }
    }, 250);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [sceneId, query, message]);

  async function reuse(fromScene: number) {
    setUsing(fromScene);
    try {
      editor.onSaved(await api<VideoDetail>(`/scenes/${sceneId}/reuse`, "POST", { scene_id: fromScene }));
      message.success("Đã dùng cho cảnh này");
      onClose();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setUsing(null);
    }
  }

  function choose(fromScene: number) {
    if (!hasPicture) {
      void reuse(fromScene);
      return;
    }
    modal.confirm({
      title: "Thay ảnh/video hiện tại của cảnh này?",
      okText: "Đổi",
      cancelText: "Huỷ",
      onOk: () => reuse(fromScene),
    });
  }

  return (
    <Modal open centered title="Ảnh/video đã dùng trong nhóm" footer={null} width={880} onCancel={onClose}>
      <Flex vertical gap={12}>
        <Input
          aria-label="Tìm ảnh đã dùng"
          prefix={<SearchOutlined />}
          placeholder="Tìm theo từ khóa hoặc chữ của cảnh (không cần dấu)…"
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Từ các video khác cùng nhóm chủ đề; khớp từ khóa của cảnh này nhất đứng trước. Bấm “Dùng” để chép sang cảnh
          này, video gốc giữ nguyên.
        </Typography.Text>
        {data === null ? (
          <Flex justify="center" style={{ padding: 32 }}>
            <Spin />
          </Flex>
        ) : data.items.length === 0 ? (
          <Empty
            description={data.total === 0 ? "Chưa video nào khác trong nhóm có ảnh hay video" : "Không có ảnh nào khớp"}
          />
        ) : (
          <div
            style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 12 }}
            data-testid="group-media"
          >
            {data.items.map((item) => (
              <Flex key={item.scene_id} vertical gap={4} data-testid="group-media-item">
                {item.kind === "clip" ? (
                  <video
                    src={`${item.url}#t=0.5`}
                    muted
                    preload="metadata"
                    style={{ width: "100%", aspectRatio: "9 / 16", objectFit: "cover", borderRadius: 6 }}
                  />
                ) : (
                  // eslint-disable-next-line @next/next/no-img-element -- the api's own file, already sized for the frame
                  <img
                    src={item.url}
                    alt={item.text.replace(/\*/g, "")}
                    loading="lazy"
                    style={{ width: "100%", aspectRatio: "9 / 16", objectFit: "cover", borderRadius: 6 }}
                  />
                )}
                <Typography.Text ellipsis={{ tooltip: item.video_title }} style={{ fontSize: 12 }}>
                  {item.kind === "clip" && <Tag style={{ marginInlineEnd: 4 }}>Video</Tag>}
                  {item.video_title}
                </Typography.Text>
                <Typography.Text
                  type="secondary"
                  ellipsis={{ tooltip: item.keywords.join(", ") }}
                  style={{ fontSize: 12 }}
                >
                  {item.keywords.join(", ") || item.text.replace(/\*/g, "")}
                </Typography.Text>
                <Button
                  size="small"
                  loading={using === item.scene_id}
                  disabled={using !== null}
                  onClick={() => choose(item.scene_id)}
                >
                  Dùng
                </Button>
              </Flex>
            ))}
          </div>
        )}
      </Flex>
    </Modal>
  );
}
