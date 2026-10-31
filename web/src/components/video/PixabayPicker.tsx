"use client";

import { SearchOutlined } from "@ant-design/icons";
import { Alert, Empty, Flex, Input, Modal, Spin, Typography } from "antd";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { api, errorMessage, type PixabayHit, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

const MAX_KEYWORDS = 10;

/** The scene's keywords with the one a photo was just chosen with put first, so "Tìm ảnh khác" starts from it. */
export function keywordsWithFirst(keywords: string[], keyword: string): string[] {
  return [keyword, ...keywords.filter((item) => item !== keyword)].slice(0, MAX_KEYWORDS);
}

/**
 * "Chọn từ Pixabay", mounted only while open. The grid shows Pixabay's small thumbnails (`preview`) straight
 * from Pixabay; choosing sends the full-size `url` with the keyword it was found with, and the server checks it
 * against that search and stores its own copy. A thumbnail is never saved anywhere.
 */
export default function PixabayPicker({
  sceneId,
  keywords,
  onClose,
}: {
  sceneId: number;
  keywords: string[];
  onClose: () => void;
}) {
  const editor = useEditor();
  const first = keywords[0] ?? "";
  const [query, setQuery] = useState(first);
  const [hits, setHits] = useState<PixabayHit[] | null>(null);
  // The keyword the shown results were found with, as the api normalised it: the choice must name the same one.
  const [searchedFor, setSearchedFor] = useState("");
  const [loading, setLoading] = useState(first.trim() !== "");
  const [choosing, setChoosing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Only the latest search may fill the grid, whatever order the answers arrive in.
  const latest = useRef(0);

  function search(text: string) {
    setLoading(true);
    setError(null);
    void load(++latest.current, text);
  }

  async function load(request: number, text: string) {
    try {
      const result = await api<{ keyword: string; hits: PixabayHit[] }>(
        `/scenes/${sceneId}/pixabay?q=${encodeURIComponent(text)}`,
      );
      if (request === latest.current) {
        setHits(result.hits);
        setSearchedFor(result.keyword);
      }
    } catch (err) {
      if (request === latest.current) {
        setError(errorMessage(err));
      }
    } finally {
      if (request === latest.current) {
        setLoading(false);
      }
    }
  }

  // Search the scene's first keyword as soon as the picker opens; with none, wait for one to be typed.
  // The spinner starts already on (see `loading`), so opening only starts the request.
  const searchOnOpen = useEffectEvent(() => {
    if (first.trim()) {
      void load(++latest.current, first);
    }
  });
  useEffect(() => {
    searchOnOpen();
  }, []);

  async function choose(hit: PixabayHit) {
    setChoosing(hit.url);
    setError(null);
    try {
      let saved = await api<VideoDetail>(`/scenes/${sceneId}/pixabay`, "POST", { keyword: searchedFor, url: hit.url });
      editor.onSaved(saved);
      if (keywords[0] !== searchedFor) {
        // Keep the keyword that found the photo, so "Tìm ảnh khác" walks on through the same results.
        saved = await api<VideoDetail>(`/scenes/${sceneId}`, "PATCH", {
          keywords: keywordsWithFirst(keywords, searchedFor),
        });
        editor.onSaved(saved);
      }
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setChoosing(null);
    }
  }

  return (
    <Modal title="Chọn từ Pixabay" open onCancel={onClose} footer={null} width={880}>
      <Input.Search
        aria-label="Từ khóa Pixabay"
        placeholder="Nhập từ khóa rồi bấm Enter, ví dụ: cá cơm chiên"
        value={query}
        enterButton={<SearchOutlined aria-label="Tìm" />}
        onChange={(event) => setQuery(event.target.value)}
        onSearch={(text) => search(text)}
        loading={loading}
        disabled={choosing !== null}
        style={{ marginBottom: 12 }}
      />
      {error && <Alert type="error" showIcon title={error} style={{ marginBottom: 12 }} data-testid="picker-error" />}
      {hits === null ? (
        loading ? (
          <Flex justify="center" style={{ padding: 32 }}>
            <Spin />
          </Flex>
        ) : (
          !error && (
            <Typography.Text type="secondary" data-testid="picker-hint">
              Cảnh này chưa có từ khóa: nhập từ khóa ở ô trên để tìm ảnh.
            </Typography.Text>
          )
        )
      ) : hits.length === 0 ? (
        <Empty description="Không có ảnh nào cho từ khóa này" />
      ) : (
        <>
          <Typography.Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
            {hits.length} ảnh từ Pixabay cho “{searchedFor}”. Bấm một ảnh để dùng cho cảnh này.
          </Typography.Text>
          {/* Columns follow the dialog's width: two on a phone, more on a wide screen; never a sideways scroll. */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
              gap: 8,
              opacity: loading ? 0.5 : 1,
            }}
          >
            {hits.map((hit, index) => (
              <button
                key={hit.url}
                type="button"
                aria-label={`Chọn ảnh ${index + 1}`}
                data-testid="pixabay-hit"
                disabled={choosing !== null || loading}
                onClick={() => choose(hit)}
                style={{
                  padding: 0,
                  border: "1px solid #EDEDED",
                  borderRadius: 6,
                  cursor: choosing !== null || loading ? "default" : "pointer",
                  background: "#F5F5F5",
                  position: "relative",
                  aspectRatio: "1 / 1",
                  overflow: "hidden",
                }}
              >
                {/* A plain <img>: a Pixabay thumbnail, only shown here and never stored. */}
                {/* eslint-disable-next-line @next/next/no-img-element -- external thumbnail, next/image would proxy it */}
                <img
                  src={hit.preview}
                  alt={`Ảnh Pixabay ${index + 1}`}
                  loading="lazy"
                  style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
                />
                {choosing === hit.url && (
                  <Flex
                    align="center"
                    justify="center"
                    style={{ position: "absolute", inset: 0, background: "rgba(255,255,255,0.6)" }}
                  >
                    <Spin />
                  </Flex>
                )}
              </button>
            ))}
          </div>
        </>
      )}
    </Modal>
  );
}
