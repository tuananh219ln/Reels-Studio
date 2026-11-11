"use client";

import { App, Button, Divider, Flex, Modal, Spin, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { FolderFilter } from "@/components/media/FolderSelect";
import MediaGrid from "@/components/media/MediaGrid";
import MediaLinkSearch from "@/components/media/MediaLinkSearch";
import { api, errorMessage, type AffiliateProduct, type MediaList, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

/**
 * "Kho tư liệu" from a scene: the library's photos and clips, opened on the folder of the product the video sells,
 * with Google Ảnh and TikTok searches for that product whose pasted links land in the same folder. "Dùng" copies the
 * item into the scene.
 */
export default function MediaLibraryPicker({
  sceneId,
  videoId,
  hasPicture,
  onClose,
}: {
  sceneId: number;
  videoId: number;
  hasPicture: boolean;
  onClose: () => void;
}) {
  const { message, modal } = App.useApp();
  const editor = useEditor();
  const [keyword, setKeyword] = useState<string | null>(null);
  const [folder, setFolder] = useState<string | null>(null);
  const [data, setData] = useState<MediaList | null>(null);
  const [using, setUsing] = useState<number | null>(null);

  // The product attached to the video names the search and the folder; without one, the video's topic.
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const video = await api<VideoDetail>(`/videos/${videoId}`);
        const products = video.affiliate_product_ids.length
          ? await api<AffiliateProduct[]>("/affiliate-products").catch(() => [] as AffiliateProduct[])
          : [];
        const name = products.find((row) => video.affiliate_product_ids.includes(row.id))?.name ?? video.topic;
        if (live) {
          setKeyword(name);
          setFolder(name.slice(0, 80).replaceAll("/", "-"));
        }
      } catch {
        if (live) {
          setKeyword("");
          setFolder("");
        }
      }
    })();
    return () => {
      live = false;
    };
  }, [videoId]);

  const load = useCallback(async () => {
    if (folder === null) return;
    try {
      const params = new URLSearchParams(folder ? { folder } : {});
      const found = await api<MediaList>(`/media?${params.toString()}`);
      // The product's folder may still be empty: then every item, newest first.
      setData(found.items.length || !folder ? found : await api<MediaList>("/media"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [folder, message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads when the folder changes; state is set only after the request answers
    void load();
  }, [load]);

  async function use(mediaId: number) {
    const go = async () => {
      setUsing(mediaId);
      try {
        editor.onSaved(await api<VideoDetail>(`/media/${mediaId}/use`, "POST", { scene_id: sceneId }));
        message.success("Đã dùng tư liệu cho cảnh");
        onClose();
      } catch (err) {
        message.error(errorMessage(err));
      } finally {
        setUsing(null);
      }
    };
    if (!hasPicture) return go();
    modal.confirm({
      title: "Thay hình của cảnh?",
      content: "Ảnh hoặc clip đang có của cảnh sẽ được thay bằng tư liệu này.",
      okText: "Thay",
      cancelText: "Huỷ",
      onOk: go,
    });
  }

  return (
    <Modal open title="Kho tư liệu" footer={null} width={900} onCancel={onClose} destroyOnHidden>
      {keyword === null || folder === null ? (
        <Spin />
      ) : (
        <Flex vertical gap={12}>
          <MediaLinkSearch keyword={keyword} folder={folder} onAdded={() => void load()} />
          <Divider style={{ margin: "4px 0" }} />
          <FolderFilter
            aria-label="Lọc theo thư mục"
            folders={data?.folders ?? []}
            value={folder || null}
            onChange={(value) => setFolder(value ?? "")}
            style={{ maxWidth: 360 }}
          />
          {data === null ? (
            <Spin />
          ) : (
            <MediaGrid
              items={data.items}
              empty="Chưa có tư liệu: tìm trên Google, TikTok rồi dán link ở trên, hoặc kéo thư mục vào trang Kho tư liệu"
              actions={(item) => [
                <Button key="use" type="link" size="small" loading={using === item.id} onClick={() => use(item.id)}>
                  Dùng
                </Button>,
              ]}
            />
          )}
          <Typography.Text type="secondary">
            Tư liệu được chép vào cảnh: xoá khỏi kho không làm hỏng video.
          </Typography.Text>
        </Flex>
      )}
    </Modal>
  );
}
