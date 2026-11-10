"use client";

import { SearchOutlined } from "@ant-design/icons";
import { Alert, Checkbox, Empty, Flex, Input, Modal, Segmented, Spin, Tag, Typography } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, type ClipHit, type PixabayHit, type StockSource, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";
import { COLORS } from "@/app/theme";

const MAX_KEYWORDS = 10;

/** The picker's filters: the photo's shape (tall by default) and whether photos the video already shows are hidden. */
type Filters = { orientation: "vertical" | "square" | "all"; hideUsed: boolean };

const ORIENTATIONS = [
  { label: "Dọc", value: "vertical" },
  { label: "Vuông", value: "square" },
  { label: "Tất cả", value: "all" },
];

/** One source search; the callers own the state, this only carries the request. */
function fetchHits(sceneId: number, text: string, sourceId: string, filters: Filters) {
  const params = new URLSearchParams({
    q: text,
    source: sourceId,
    orientation: filters.orientation,
    hide_used: String(filters.hideUsed),
  });
  return api<{ keyword: string; source: string; hits: PixabayHit[] }>(`/scenes/${sceneId}/stock?${params.toString()}`);
}

/** The scene's keywords with the one a photo was just chosen with put first, so "Tìm ảnh" starts from it. */
export function keywordsWithFirst(keywords: string[], keyword: string): string[] {
  return [keyword, ...keywords.filter((item) => item !== keyword)].slice(0, MAX_KEYWORDS);
}

/** The app's first stock library: used only when the api's list of sources cannot be read. */
export const DEFAULT_SOURCE = "pexels";

/** Sources that index Vietnamese titles (community uploads): searched with the scene's Vietnamese keywords. */
export const VIETNAMESE_FIRST = new Set(["wikimedia", "openverse"]);

/**
 * The keyword a source opens with: Wikimedia and Openverse are searched with the Vietnamese terms, the
 * Western libraries with the English ones; either list backs the other up when it is empty.
 */
function firstKeyword(sourceId: string, keywords: string[], keywordsEn: string[]): string {
  const vietnamese = VIETNAMESE_FIRST.has(sourceId);
  const preferred = vietnamese ? keywords : keywordsEn;
  const fallback = vietnamese ? keywordsEn : keywords;
  return preferred[0] ?? fallback[0] ?? "";
}

/** The picker's source switch: usable sources, and those waiting for a key greyed out with the reason. */
function sourceOptions(sources: StockSource[]) {
  return sources.map((item) => ({
    label: item.available ? item.label : `${item.label} (chưa cấu hình key)`,
    value: item.id,
    disabled: !item.available,
    title: item.available ? undefined : "Dán key ở Cài đặt › Nguồn tư liệu để dùng nguồn này",
  }));
}

/**
 * "Chọn từ kho ảnh/video", mounted only while open; its "Video" mode is ClipPicker below. Sources come from the
 * api in the video's topic group's order ("Thứ tự nguồn ảnh"); the picker opens on the first usable one, shows a
 * source without its key greyed out, and leaves out one turned off. Each source opens in the language it indexes
 * (English for Pexels/Unsplash/Pixabay, Vietnamese for Wikimedia/Openverse) unless the member typed a keyword. The grid
 * shows each source's small thumbnails (`preview`) straight from the source; choosing sends the
 * full-size `url` with the keyword and the source it was found with, and the server checks it against
 * that search and stores its own copy. A thumbnail is never saved anywhere.
 */
export default function StockPicker({
  sceneId,
  videoId,
  keywords: liveKeywords,
  keywordsEn: liveKeywordsEn,
  onClose,
}: {
  sceneId: number;
  videoId: number;
  keywords: string[];
  keywordsEn: string[];
  onClose: () => void;
}) {
  const editor = useEditor();
  // The keywords as they were when the picker opened. The page polls the video every few seconds and
  // each poll hands new (equal) arrays; following them would restart the picker and drop the chosen
  // source. The choice itself still reorders the latest lists (see choose()).
  const [{ keywords, keywordsEn }] = useState({ keywords: liveKeywords, keywordsEn: liveKeywordsEn });
  const first = firstKeyword(DEFAULT_SOURCE, keywords, keywordsEn);
  const [query, setQuery] = useState(first);
  const [sources, setSources] = useState<StockSource[] | null>(null);
  const [source, setSource] = useState(DEFAULT_SOURCE);
  const [hits, setHits] = useState<PixabayHit[] | null>(null);
  // The keyword and source the shown results were found with, as the api normalised them:
  // the choice must name the same pair.
  const [searchedFor, setSearchedFor] = useState("");
  const [searchedSource, setSearchedSource] = useState(DEFAULT_SOURCE);
  const [loading, setLoading] = useState(first.trim() !== "");
  const [choosing, setChoosing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<"photo" | "clip">("photo");
  const [filters, setFilters] = useState<Filters>({ orientation: "vertical", hideUsed: true });
  // The orientation the shown results were found with: the choice is checked against the same search.
  const [searchedOrientation, setSearchedOrientation] = useState<Filters["orientation"]>("vertical");
  // Only the latest search may fill the grid, whatever order the answers arrive in.
  const latest = useRef(0);
  // True while the picker is mounted: an answer that arrives after it closed changes nothing.
  const open = useRef(false);
  // True once the member has typed or searched: the opening search, whose sources answer may arrive later,
  // then leaves their keyword and their results alone.
  const touched = useRef(false);

  function search(text: string, sourceId: string, using: Filters = filters) {
    touched.current = true;
    setLoading(true);
    setError(null);
    void load(++latest.current, text, sourceId, using);
  }

  async function load(request: number, text: string, sourceId: string, using: Filters = filters) {
    try {
      const result = await fetchHits(sceneId, text, sourceId, using);
      if (request === latest.current) {
        setHits(result.hits);
        setSearchedFor(result.keyword);
        setSearchedSource(result.source);
        setSearchedOrientation(using.orientation);
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
  // one (Pexels when configured, else the first offered); with no keyword, wait for one to be typed.
  // If the sources call itself fails, fall back to Pexels alone so the picker still works. Every state
  // change happens in a promise callback, after checking the picker is still open; `keywords` are the
  // snapshot taken at open, so this runs once per opening.
  useEffect(() => {
    open.current = true;
    api<StockSource[]>(`/stock/sources?video_id=${videoId}`)
      .then(
        // A source turned off on Cài đặt is left out; one waiting for its key stays, greyed out.
        (all) => all.filter((item) => item.available || item.missing_key),
        () => [],
      )
      .then((listed) => {
        if (!open.current) {
          return;
        }
        const usable = listed.filter((item) => item.available);
        const offered =
          usable.length > 0 ? listed : [{ id: DEFAULT_SOURCE, label: "Pexels", available: true }, ...listed];
        setSources(offered);
        // The first usable source of the group's order.
        const initial = offered.find((item) => item.available)?.id ?? DEFAULT_SOURCE;
        setSource(initial);
        setSearchedSource(initial);
        // The member was quicker than the sources answer: what they typed or searched stays.
        if (touched.current) {
          return;
        }
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
  }, [keywords, keywordsEn, sceneId, videoId]);

  /** A filter changed: the shown keyword is searched again with it. */
  function changeFilters(next: Filters) {
    setFilters(next);
    if (query.trim()) {
      search(query, source, next);
    }
  }

  const chips = Array.from(
    new Set(VIETNAMESE_FIRST.has(source) ? [...keywords, ...keywordsEn] : [...keywordsEn, ...keywords]),
  ).filter((keyword) => keyword.trim());

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
        orientation: searchedOrientation,
      });
      editor.onSaved(saved);
      // Keep the keyword that found the photo at the head of the list its source reads, so the
      // next search walks on through the same results: Wikimedia and Openverse read the Vietnamese
      // list, "Tìm ảnh" reads the list of the source it searches.
      const vietnamese = VIETNAMESE_FIRST.has(searchedSource);
      const list = vietnamese ? liveKeywords : liveKeywordsEn;
      if (list[0] !== searchedFor) {
        saved = await api<VideoDetail>(
          `/scenes/${sceneId}`,
          "PATCH",
          vietnamese
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

  const sourceLabel = sources?.find((item) => item.id === searchedSource)?.label ?? "Pexels";
  const clipSources = (sources ?? []).filter((item) => item.clips);

  return (
    <Modal
      title="Chọn từ kho ảnh/video"
      open
      centered
      onCancel={onClose}
      footer={null}
      width={880}
      // In the middle of the screen, the grid scrolling inside it rather than the page.
      styles={{ body: { maxHeight: "calc(100vh - 140px)", overflowY: "auto", overflowX: "hidden" } }}
    >
      {clipSources.length > 0 && (
        <Segmented
          aria-label="Loại tư liệu"
          value={kind}
          onChange={(value) => setKind(value as "photo" | "clip")}
          options={[
            { label: "Ảnh", value: "photo" },
            { label: "Video", value: "clip" },
          ]}
          disabled={choosing !== null}
          style={{ marginBottom: 12, marginRight: 12 }}
        />
      )}
      {kind === "clip" ? (
        <ClipPicker
          sceneId={sceneId}
          sources={clipSources}
          opening={firstKeyword("pexels", keywords, keywordsEn)}
          onClose={onClose}
        />
      ) : (
        <>
          {sources !== null && sources.length > 1 && (
            <Segmented
              aria-label="Nguồn ảnh"
              value={source}
              onChange={(value) => switchSource(String(value))}
              options={sourceOptions(sources)}
              disabled={choosing !== null}
              style={{ marginBottom: 12, maxWidth: "100%", overflowX: "auto" }}
            />
          )}
          <Input.Search
            aria-label="Từ khóa tìm ảnh"
            placeholder="Nhập từ khóa rồi bấm Enter, ví dụ: cá cơm chiên…"
            value={query}
            enterButton={<SearchOutlined aria-label="Tìm" />}
            onChange={(event) => {
              touched.current = true;
              setQuery(event.target.value);
            }}
            onSearch={(text) => search(text, source)}
            // No `loading` here: antd ignores Enter while the box shows it, so a keyword typed during the
            // opening search was never searched. The grid fades while loading, and the latest search wins.
            disabled={choosing !== null}
            style={{ marginBottom: 8 }}
          />
          {/* The scene's keywords, in the source's language first: one tap searches it. */}
          {chips.length > 0 && (
            <Flex wrap gap={6} style={{ marginBottom: 8 }} data-testid="keyword-chips">
              {chips.map((keyword) => (
                <Tag.CheckableTag
                  key={keyword}
                  checked={keyword === query}
                  onChange={() => {
                    if (choosing === null) {
                      setQuery(keyword);
                      search(keyword, source);
                    }
                  }}
                >
                  {keyword}
                </Tag.CheckableTag>
              ))}
            </Flex>
          )}
          <Flex wrap gap={12} align="center" style={{ marginBottom: 12 }}>
            <Segmented
              aria-label="Hướng ảnh"
              size="small"
              value={filters.orientation}
              options={ORIENTATIONS}
              disabled={choosing !== null}
              onChange={(value) => changeFilters({ ...filters, orientation: value as Filters["orientation"] })}
            />
            <Checkbox
              checked={filters.hideUsed}
              disabled={choosing !== null}
              onChange={(event) => changeFilters({ ...filters, hideUsed: event.target.checked })}
            >
              Ẩn ảnh đã dùng trong video này
            </Checkbox>
          </Flex>
          {error && (
            <Alert type="error" showIcon title={error} style={{ marginBottom: 12 }} data-testid="picker-error" />
          )}
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
              {/* Columns follow the dialog's width: two on a phone, more on a wide screen; never a sideways scroll.
                  Each tile is 9:16 and filled, cropped as the render will crop the photo. */}
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
                    className="stock-tile"
                    disabled={choosing !== null || loading}
                    onClick={() => choose(hit)}
                    style={{
                      padding: 0,
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: 8,
                      cursor: choosing !== null || loading ? "default" : "pointer",
                      background: COLORS.muted,
                      position: "relative",
                      aspectRatio: "9 / 16",
                      overflow: "hidden",
                    }}
                  >
                    {/* A plain <img>: a source thumbnail, only shown here and never stored. */}
                    {/* eslint-disable-next-line @next/next/no-img-element -- external thumbnail, next/image would proxy it */}
                    <img
                      src={hit.preview}
                      alt={`Ảnh ${sourceLabel} ${index + 1}`}
                      loading="lazy"
                      style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                    />
                    {hit.credit && (
                      // A photo whose licence asks for credit (Wikimedia CC BY...): usable, but the post must name it.
                      <span
                        title={hit.credit}
                        data-testid="stock-hit-credit"
                        style={{
                          position: "absolute",
                          left: 4,
                          right: 4,
                          bottom: 4,
                          padding: "2px 6px",
                          borderRadius: 4,
                          background: "rgba(0,0,0,0.65)",
                          color: "#fff",
                          fontSize: 11,
                          lineHeight: 1.3,
                          textAlign: "left",
                        }}
                      >
                        Cần ghi nguồn
                      </span>
                    )}
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
        </>
      )}
    </Modal>
  );
}

/**
 * The picker's "Video" mode: vertical stock clips from Pexels and Pixabay. A still and the length show in the
 * grid; pointing at one plays it, muted, straight from the source. Choosing sends its id with the keyword and
 * source it was found with; the api searches again, downloads that file and stores it like an upload, in place
 * of the scene's photo or clip.
 */
function ClipPicker({
  sceneId,
  sources,
  opening,
  onClose,
}: {
  sceneId: number;
  sources: StockSource[];
  opening: string;
  onClose: () => void;
}) {
  const editor = useEditor();
  const [source, setSource] = useState(sources[0].id);
  const [query, setQuery] = useState(opening);
  const [hits, setHits] = useState<ClipHit[] | null>(null);
  const [searched, setSearched] = useState({ keyword: "", source: sources[0].id });
  const [loading, setLoading] = useState(false);
  const [choosing, setChoosing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);

  const search = useCallback(
    async (text: string, sourceId: string) => {
      if (!text.trim()) {
        return;
      }
      const request = ++latest.current;
      setLoading(true);
      setError(null);
      try {
        const result = await api<{ keyword: string; source: string; hits: ClipHit[] }>(
          `/scenes/${sceneId}/stock-clips?q=${encodeURIComponent(text)}&source=${sourceId}`,
        );
        if (request === latest.current) {
          setHits(result.hits);
          setSearched({ keyword: result.keyword, source: result.source });
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
    },
    [sceneId],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- searches the opening keyword once when the Video mode opens
    void search(opening, sources[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per opening of the Video mode
  }, []);

  async function choose(hit: ClipHit) {
    setChoosing(hit.id);
    setError(null);
    try {
      editor.onSaved(
        await api<VideoDetail>(`/scenes/${sceneId}/stock-clips`, "POST", {
          source: searched.source,
          keyword: searched.keyword,
          id: hit.id,
        }),
      );
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setChoosing(null);
    }
  }

  const label = sources.find((item) => item.id === searched.source)?.label ?? "";
  return (
    <>
      {sources.length > 1 && (
        <Segmented
          aria-label="Nguồn video"
          value={source}
          onChange={(value) => {
            setSource(String(value));
            void search(query, String(value));
          }}
          options={sources.map((item) => ({ label: item.label, value: item.id }))}
          disabled={choosing !== null}
          style={{ marginBottom: 12 }}
        />
      )}
      <Input.Search
        aria-label="Từ khóa tìm video"
        placeholder="Nhập từ khóa tiếng Anh rồi bấm Enter, ví dụ: fried fish…"
        value={query}
        enterButton={<SearchOutlined aria-label="Tìm" />}
        onChange={(event) => setQuery(event.target.value)}
        onSearch={(text) => search(text, source)}
        // No `loading`: antd would ignore Enter while it shows; the latest search wins (see the photo box).
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
          !error && <Typography.Text type="secondary">Nhập từ khóa ở ô trên để tìm video.</Typography.Text>
        )
      ) : hits.length === 0 ? (
        <Empty description="Không có video nào cho từ khóa này" />
      ) : (
        <>
          <Typography.Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
            {hits.length} video từ {label} cho “{searched.keyword}”. Rê chuột để xem, bấm để dùng cho cảnh này (thay ảnh
            hoặc video hiện có).
          </Typography.Text>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))",
              gap: 8,
              opacity: loading ? 0.5 : 1,
            }}
          >
            {hits.map((hit, index) => (
              <button
                key={hit.id}
                type="button"
                aria-label={`Chọn video ${index + 1}`}
                data-testid="clip-hit"
                className="stock-tile"
                disabled={choosing !== null || loading}
                onClick={() => choose(hit)}
                style={{
                  padding: 0,
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: 6,
                  background: "#000",
                  position: "relative",
                  aspectRatio: "9 / 16",
                  overflow: "hidden",
                  cursor: choosing !== null || loading ? "default" : "pointer",
                }}
              >
                <video
                  src={hit.url}
                  poster={hit.preview}
                  muted
                  loop
                  playsInline
                  preload="none"
                  onMouseEnter={(event) => void event.currentTarget.play().catch(() => undefined)}
                  onMouseLeave={(event) => event.currentTarget.pause()}
                  style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                />
                <span
                  style={{
                    position: "absolute",
                    right: 4,
                    bottom: 4,
                    background: "rgba(0,0,0,0.65)",
                    color: "#fff",
                    fontSize: 11,
                    padding: "1px 5px",
                    borderRadius: 4,
                  }}
                >
                  {Math.round(hit.seconds)} giây
                </span>
                {choosing === hit.id && (
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
    </>
  );
}
