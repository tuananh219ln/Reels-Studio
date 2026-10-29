"use client";

import { SearchOutlined } from "@ant-design/icons";
import { Alert, Empty, Flex, Input, Modal, Spin, Typography } from "antd";
import { useEffect, useState } from "react";
import { api, errorMessage, type PixabayHit, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

/**
 * "Chọn từ Pixabay": thumbnails come straight from Pixabay and are only shown while choosing; the chosen
 * photo is downloaded by the server and stored with the video (no hotlinking).
 */
export default function PixabayPicker({
  sceneId,
  keyword,
  open,
  onClose,
}: {
  sceneId: number;
  keyword: string;
  open: boolean;
  onClose: () => void;
}) {
  const editor = useEditor();
  const [query, setQuery] = useState(keyword);
  const [hits, setHits] = useState<PixabayHit[] | null>(null);
  const [searchedFor, setSearchedFor] = useState("");
  const [loading, setLoading] = useState(false);
  const [choosing, setChoosing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function search(text: string) {
    if (!text.trim()) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await api<{ keyword: string; hits: PixabayHit[] }>(
        `/scenes/${sceneId}/pixabay?q=${encodeURIComponent(text)}`,
      );
      setHits(result.hits);
      setSearchedFor(result.keyword);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (open) {
      setQuery(keyword);
      setHits(null);
      void search(keyword);
    }
    // Search when the dialog opens; afterwards a new keyword is searched on Enter.
  }, [open]);

  async function choose(hit: PixabayHit) {
    setChoosing(hit.url);
    setError(null);
    try {
      editor.onSaved(
        await api<VideoDetail>(`/scenes/${sceneId}/pixabay`, "POST", { keyword: searchedFor, url: hit.url }),
      );
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setChoosing(null);
    }
  }

  return (
    <Modal title="Chọn từ Pixabay" open={open} onCancel={onClose} footer={null} width={760} destroyOnHidden>
      <Input.Search
        aria-label="Từ khóa Pixabay"
        value={query}
        enterButton={<SearchOutlined />}
        onChange={(event) => setQuery(event.target.value)}
        onSearch={(text) => search(text)}
        loading={loading}
        style={{ marginBottom: 12 }}
      />
      {error && <Alert type="error" showIcon title={error} style={{ marginBottom: 12 }} data-testid="picker-error" />}
      <Typography.Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
        Ảnh từ Pixabay
      </Typography.Text>
      {loading && hits === null ? (
        <Flex justify="center" style={{ padding: 32 }}>
          <Spin />
        </Flex>
      ) : hits && hits.length === 0 ? (
        <Empty description="Không có ảnh nào cho từ khóa này" />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 8 }}>
          {hits?.map((hit) => (
            <button
              key={hit.url}
              type="button"
              aria-label="Chọn ảnh này"
              data-testid="pixabay-hit"
              disabled={choosing !== null}
              onClick={() => choose(hit)}
              style={{ padding: 0, border: "1px solid #EDEDED", borderRadius: 6, cursor: "pointer",
                background: "#FAFAFA", position: "relative", aspectRatio: "1 / 1", overflow: "hidden" }}
            >
              <img src={hit.preview} alt="" loading="lazy"
                style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
              {choosing === hit.url && (
                <Flex align="center" justify="center"
                  style={{ position: "absolute", inset: 0, background: "rgba(255,255,255,0.6)" }}>
                  <Spin />
                </Flex>
              )}
            </button>
          ))}
        </div>
      )}
    </Modal>
  );
}
