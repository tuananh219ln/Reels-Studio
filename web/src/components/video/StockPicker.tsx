"use client";

import { SearchOutlined } from "@ant-design/icons";
import { Alert, Empty, Flex, Input, Modal, Segmented, Spin, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { api, errorMessage, type PixabayHit, type StockSource, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

const MAX_KEYWORDS = 10;

/** One source search; the callers own the state, this only carries the request. */
function fetchHits(sceneId: number, text: string, sourceId: string) {
  return api<{ keyword: string; source: string; hits: PixabayHit[] }>(
    `/scenes/${sceneId}/stock?q=${encodeURIComponent(text)}&source=${sourceId}`,
  );
}

/** The scene's keywords with the one a photo was just chosen with put first, so "Tìm ảnh khác" starts from it. */
export function keywordsWithFirst(keywords: string[], keyword: string): string[] {
  return [keyword, ...keywords.filter((item) => item !== keyword)].slice(0, MAX_KEYWORDS);
}

/**
 * The keyword a source opens with: Openverse is searched with the Vietnamese terms (its photos are
 * community uploads, titled in Vietnamese), the Western libraries with the English ones; either
 * list backs the other up when it is empty.
 */
function firstKeyword(sourceId: string, keywords: string[], keywordsEn: string[]): string {
  const preferred = sourceId === "openverse" ? keywords : keywordsEn;
  const fallback = sourceId === "openverse" ? keywordsEn : keywords;
  return preferred[0] ?? fallback[0] ?? "";
}

/**
 * "Chọn từ kho ảnh", mounted only while open. Sources (Pixabay, Pexels, Openverse) come from the api,
 * which hides one that is not configured; each source opens in the language it indexes (English for
 * Pixabay/Pexels, Vietnamese for Openverse) unless the member typed a keyword of their own. The grid
 * shows each source's small thumbnails (`preview`) straight from the source; choosing sends the
 * full-size `url` with the keyword and the source it was found with, and the server checks it against
 * that search and stores its own copy. A thumbnail is never saved anywhere.
 */
export default function StockPicker({
  sceneId,
  keywords: liveKeywords,
  keywordsEn: liveKeywordsEn,
  onClose,
}: {
  sceneId: number;
  keywords: string[];
  keywordsEn: string[];
  onClose: () => void;
}) {
  const editor = useEditor();
  // The keywords as they were when the picker opened. The page polls the video every few seconds and
  // each poll hands new (equal) arrays; following them would restart the picker and drop the chosen
  // source. The choice itself still reorders the latest lists (see choose()).
  const [{ keywords, keywordsEn }] = useState({ keywords: liveKeywords, keywordsEn: liveKeywordsEn });
  const first = firstKeyword("pixabay", keywords, keywordsEn);
  const [query, setQuery] = useState(first);
  const [sources, setSources] = useState<StockSource[] | null>(null);
  const [source, setSource] = useState("pixabay");
  const [hits, setHits] = useState<PixabayHit[] | null>(null);
  // The keyword and source the shown results were found with, as the api normalised them:
  // the choice must name the same pair.
  const [searchedFor, setSearchedFor] = useState("");
  const [searchedSource, setSearchedSource] = useState("pixabay");
  const [loading, setLoading] = useState(first.trim() !== "");
  const [choosing, setChoosing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Only the latest search may fill the grid, whatever order the answers arrive in.
  const latest = useRef(0);
  // True while the picker is mounted: an answer that arrives after it closed changes nothing.
  const open = useRef(false);

  function search(text: string, sourceId: string) {
    setLoading(true);
    setError(null);
    void load(++latest.current, text, sourceId);
  }

  async function load(request: number, text: string, sourceId: string) {
    try {
      const result = await fetchHits(sceneId, text, sourceId);
      if (request === latest.current) {
        setHits(result.hits);
        setSearchedFor(result.keyword);
        setSearchedSource(result.source);
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

  // On open: learn which sources the api offers, then search the scene's first keyword in the default
  // one (Pixabay when configured, else the first offered); with no keyword, wait for one to be typed.
  // If the sources call itself fails, fall back to Pixabay alone so the picker still works. Every state
  // change happens in a promise callback, after checking the picker is still open; `keywords` are the
  // snapshot taken at open, so this runs once per opening.
  useEffect(() => {
    open.current = true;
    api<StockSource[]>("/stock/sources")
      .then(
        (all) => all.filter((item) => item.available),
        () => [],
      )
      .then((available) => {
        if (!open.current) {
          return;
        }
        const offered = available.length > 0 ? available : [{ id: "pixabay", label: "Pixabay", available: true }];
        setSources(offered);
        const initial = offered.some((item) => item.id === "pixabay") ? "pixabay" : offered[0].id;
        setSource(initial);
        setSearchedSource(initial);
        const opening = firstKeyword(initial, keywords, keywordsEn);
        setQuery(opening);
        // With no keyword there is nothing to search; `loading` already started false for that case.
        if (opening.trim()) {
          void load(++latest.current, opening, initial);
        }
      });
    return () => {
      open.current = false;
    };
    // `load` is a plain function that changes every render; depending on it would re-run this each time.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once per opening, see above
  }, [keywords, keywordsEn, sceneId]);

  function switchSource(next: string) {
    setSource(next);
    // An untouched box still holds the previous source's opening keyword: swap it for the new
    // source's, so every library is searched in its own language. A typed keyword stays as typed.
    const text =
      query === firstKeyword(source, keywords, keywordsEn) ? firstKeyword(next, keywords, keywordsEn) : query;
    if (text !== query) {
      setQuery(text);
    }
    if (text.trim()) {
      search(text, next);
    }
  }

  async function choose(hit: PixabayHit) {
    setChoosing(hit.url);
    setError(null);
    try {
      let saved = await api<VideoDetail>(`/scenes/${sceneId}/stock`, "POST", {
        source: searchedSource,
        keyword: searchedFor,
        url: hit.url,
      });
      editor.onSaved(saved);
      // Keep the keyword that found the photo at the head of the list its source reads, so the
      // next search walks on through the same results: Openverse reads the Vietnamese list,
      // "Tìm ảnh khác" reads the list of the source it searches.
      const onOpenverse = searchedSource === "openverse";
      const list = onOpenverse ? liveKeywords : liveKeywordsEn;
      if (list[0] !== searchedFor) {
        saved = await api<VideoDetail>(
          `/scenes/${sceneId}`,
          "PATCH",
          onOpenverse
            ? { keywords: keywordsWithFirst(liveKeywords, searchedFor) }
            : { keywords_en: keywordsWithFirst(liveKeywordsEn, searchedFor) },
        );
        editor.onSaved(saved);
      }
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setChoosing(null);
    }
  }

  const sourceLabel = sources?.find((item) => item.id === searchedSource)?.label ?? "Pixabay";

  return (
    <Modal title="Chọn từ kho ảnh" open onCancel={onClose} footer={null} width={880}>
      {sources !== null && sources.length > 1 && (
        <Segmented
          aria-label="Nguồn ảnh"
          value={source}
          onChange={(value) => switchSource(String(value))}
          options={sources.map((item) => ({ label: item.label, value: item.id }))}
          disabled={choosing !== null}
          style={{ marginBottom: 12 }}
        />
      )}
      <Input.Search
        aria-label="Từ khóa tìm ảnh"
        placeholder="Nhập từ khóa rồi bấm Enter, ví dụ: cá cơm chiên"
        value={query}
        enterButton={<SearchOutlined aria-label="Tìm" />}
        onChange={(event) => setQuery(event.target.value)}
        onSearch={(text) => search(text, source)}
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
            {hits.length} ảnh từ {sourceLabel} cho “{searchedFor}”. Bấm một ảnh để dùng cho cảnh này.
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
                data-testid="stock-hit"
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
                {/* A plain <img>: a source thumbnail, only shown here and never stored. */}
                {/* eslint-disable-next-line @next/next/no-img-element -- external thumbnail, next/image would proxy it */}
                <img
                  src={hit.preview}
                  alt={`Ảnh ${sourceLabel} ${index + 1}`}
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
