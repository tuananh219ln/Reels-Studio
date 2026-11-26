"use client";

import { DownOutlined, PlayCircleOutlined } from "@ant-design/icons";
import { App, Button, Card, Dropdown, Flex, Input, Tag, Tooltip, Typography } from "antd";
import { useEffect, useState } from "react";
import {
  api,
  errorMessage,
  type StrategyCatalog,
  type VideoBeat,
  type VideoDetail,
  type VideoStrategy,
} from "@/lib/api";
import { useEditor } from "./AutoSaveField";

/** Tag colours by beat type: the problem in red, the answer in green, the call to act in the brand's orange. */
const BEAT_COLORS: Record<string, string> = {
  hook: "orange",
  pain: "red",
  conflict: "red",
  myth: "red",
  solution: "green",
  item: "green",
  truth: "green",
  after: "green",
  resolution: "green",
  proof: "blue",
  setup: "blue",
  before: "default",
  turning_point: "purple",
  cta: "volcano",
};

/** Asks the MP4's player (the "Đăng bài" tab's small video) to open at a second. */
export const PLAY_MP4_EVENT = "reels:play-mp4";

const STRATEGY_FIELDS: { key: keyof Omit<VideoStrategy, "content_type">; label: string }[] = [
  { key: "audience", label: "Đối tượng" },
  { key: "pain_point", label: "Nỗi đau" },
  { key: "promise", label: "Lời hứa" },
];

/**
 * The left column of a video Muse wrote with beats (docs/decisions/2026-11-26-strategy-beats.md): "Chiến lược nội
 * dung" (its kind and three lines to edit) and "Kịch bản theo nhịp", one row per beat with its seconds and its text to
 * edit in place. A hook has "Đổi hook" with the other hooks Muse wrote; a changed text goes to the scene the beat
 * names, so the MP4 is outdated until it is rendered again. A row's QC items show on it, and its seconds open the MP4
 * there.
 */
export default function StrategyColumn({ video, onOpenProducts }: { video: VideoDetail; onOpenProducts: () => void }) {
  const { message } = App.useApp();
  const editor = useEditor();
  const [catalog, setCatalog] = useState<StrategyCatalog | null>(null);
  useEffect(() => {
    let live = true;
    api<StrategyCatalog>("/strategy/catalog").then(
      (found) => live && setCatalog(found),
      () => {},
    );
    return () => {
      live = false;
    };
  }, []);
  const disabled = editor.locked || editor.readOnly;
  const strategy = video.strategy;
  const beats = video.beats ?? [];
  const items = video.review?.qc.items ?? [];

  async function save(body: { strategy?: VideoStrategy; beats?: VideoBeat[] }, field: string) {
    const request = api<VideoDetail>(`/strategy/${video.id}`, "PUT", body);
    editor.track(request);
    try {
      editor.onSaved(await request);
      editor.reportFailed(field, false);
    } catch (err) {
      editor.reportFailed(field, true);
      message.error(errorMessage(err));
    }
  }

  function editBeat(beat: VideoBeat, text: string) {
    if (text === beat.text) return;
    void save({ beats: beats.map((one) => (one.id === beat.id ? { ...one, text } : one)) }, `beat-${beat.id}`);
  }

  function swapHook(beat: VideoBeat, index: number) {
    const chosen = beat.alt_hooks?.[index];
    if (chosen === undefined) return;
    // The hook it replaces becomes one of the choices, so the member can swap back.
    const others = (beat.alt_hooks ?? []).filter((_, at) => at !== index);
    editBeatWith({ ...beat, text: chosen, alt_hooks: [beat.text, ...others].filter(Boolean).slice(0, 5) });
  }

  function editBeatWith(next: VideoBeat) {
    void save({ beats: beats.map((one) => (one.id === next.id ? next : one)) }, `beat-${next.id}`);
  }

  return (
    <Flex vertical gap={16} data-testid="strategy-column">
      {strategy && (
        <Card size="small" title="Chiến lược nội dung" data-testid="strategy-card">
          <Flex vertical gap={10}>
            <Flex align="center" gap={8} wrap>
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                Kiểu nội dung
              </Typography.Text>
              <Tooltip title="Muốn đổi kiểu, nhờ Muse làm bản mới theo kiểu khác">
                <Tag color="orange" style={{ margin: 0 }} data-testid="strategy-type">
                  {catalog?.content_types.find((type) => type.code === strategy.content_type)?.name ??
                    strategy.content_type}
                </Tag>
              </Tooltip>
            </Flex>
            {STRATEGY_FIELDS.map(({ key, label }) => (
              <Flex key={`${key}:${strategy[key]}`} gap={8} align="flex-start">
                <Typography.Text type="secondary" style={{ flex: "none", width: 72, fontSize: 13, paddingTop: 4 }}>
                  {label}
                </Typography.Text>
                <Input.TextArea
                  aria-label={label}
                  autoSize={{ minRows: 1, maxRows: 4 }}
                  defaultValue={strategy[key]}
                  disabled={disabled}
                  maxLength={300}
                  onBlur={(event) => {
                    if (event.target.value !== strategy[key])
                      void save({ strategy: { ...strategy, [key]: event.target.value } }, `strategy-${key}`);
                  }}
                />
              </Flex>
            ))}
          </Flex>
        </Card>
      )}
      <Card size="small" title="Kịch bản theo nhịp" data-testid="beats-card">
        <Flex vertical gap={12}>
          {beats.map((beat) => {
            const here = items.filter((item) => item.beat === beat.id);
            return (
              <Flex key={beat.id} vertical gap={6} data-testid="beat" data-beat={beat.id}>
                <Flex align="center" gap={8} wrap>
                  <Tag color={BEAT_COLORS[beat.type] ?? "default"} style={{ margin: 0 }}>
                    {catalog?.beat_types.find((type) => type.code === beat.type)?.name ?? beat.type}
                  </Tag>
                  <Button
                    type="link"
                    size="small"
                    icon={<PlayCircleOutlined />}
                    style={{ padding: 0, height: "auto", fontSize: 13 }}
                    aria-label={`Xem từ giây ${beat.start}`}
                    onClick={() =>
                      window.dispatchEvent(new CustomEvent(PLAY_MP4_EVENT, { detail: { at: beat.start } }))
                    }
                  >
                    {beat.start}–{beat.end}s
                  </Button>
                  {beat.type === "hook" && (beat.alt_hooks?.length ?? 0) > 0 && (
                    <Dropdown
                      trigger={["click"]}
                      disabled={disabled}
                      menu={{
                        items: (beat.alt_hooks ?? []).map((hook, index) => ({ key: index, label: hook })),
                        onClick: ({ key }) => swapHook(beat, Number(key)),
                      }}
                    >
                      <Button size="small" type="link" data-testid="beat-swap-hook" style={{ marginLeft: "auto" }}>
                        Đổi hook <DownOutlined style={{ fontSize: 10 }} />
                      </Button>
                    </Dropdown>
                  )}
                  {beat.type === "cta" && (
                    <Button
                      size="small"
                      type="link"
                      style={{ marginLeft: "auto" }}
                      onClick={onOpenProducts}
                      data-testid="beat-products"
                    >
                      {beat.affiliate_product_id ? "Đổi sản phẩm affiliate" : "Gắn sản phẩm affiliate"}
                    </Button>
                  )}
                </Flex>
                <Input.TextArea
                  key={`${beat.id}:${beat.text}`}
                  aria-label={`Nhịp ${beat.id}`}
                  autoSize={{ minRows: 1, maxRows: 6 }}
                  defaultValue={beat.text}
                  disabled={disabled}
                  maxLength={600}
                  onBlur={(event) => editBeat(beat, event.target.value)}
                />
                {beat.items && beat.items.length > 0 && (
                  <Typography.Text type="secondary" style={{ fontSize: 12.5 }}>
                    {beat.items.join(" · ")}
                  </Typography.Text>
                )}
                {here.map((item, index) => (
                  <Typography.Text
                    key={`${item.code}-${index}`}
                    type={item.level === "blocker" ? "danger" : "warning"}
                    style={{ fontSize: 12.5 }}
                  >
                    {item.message}
                  </Typography.Text>
                ))}
              </Flex>
            );
          })}
        </Flex>
      </Card>
    </Flex>
  );
}
