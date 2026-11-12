"use client";

import { BulbOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Flex, Spin, Switch, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { api, errorMessage, type Knowledge, type KnowledgeTopic, type VideoOptions } from "@/lib/api";
import EditHistory from "@/components/EditHistory";
import { TextSettings, type SettingsValues } from "@/components/video/VideoSettings";
import { palette, STYLES } from "@/components/video/textPalette";

type Update = (body: Partial<KnowledgeTopic>) => Promise<KnowledgeTopic>;
type Look = Partial<VideoOptions>;

// The fields of "Chữ & phụ đề" (api text_looks.FIELDS), in the order the editor shows them.
const FIELDS = [
  "text_style",
  "text_color",
  "title_style",
  "box_color",
  "accent_color",
  "box_opacity",
  "title_text_style",
  "title_text_color",
  "title_box_color",
  "title_accent_color",
  "title_box_opacity",
  "text_size",
  "title_text_size",
  "text_case",
  "title_text_case",
  "captions",
] as const;
// How often the card reads the group again while "AI gợi ý" is being made (one LLM call, a few seconds).
const POLL_MS = 3000;

function pick(look: Look): Look {
  return Object.fromEntries(FIELDS.filter((name) => look[name] !== undefined).map((name) => [name, look[name]]));
}

function sameLook(first: Look | null, second: Look | null): boolean {
  return JSON.stringify(first ? pick(first) : null) === JSON.stringify(second ? pick(second) : null);
}

/** A few words for each value a suggestion sets, so a look can be judged before it is put in the editor. */
function describe(look: Look): string[] {
  const words: string[] = [];
  const style = STYLES.find((item) => item.value === look.text_style);
  if (style) {
    words.push(
      style.value === "none" ? "Không hộp" : style.value === "box" ? "Hộp màu" : `Hộp ${style.label.toLowerCase()}`,
    );
  }
  if (look.text_size) words.push({ large: "Chữ lớn", medium: "Chữ vừa", small: "Chữ nhỏ" }[look.text_size]);
  if (look.text_case) words.push(look.text_case === "upper" ? "VIẾT HOA" : "Giữ chữ như kịch bản");
  if (look.captions) {
    words.push({ off: "Không phụ đề", phrase: "Phụ đề từng cụm", word: "Phụ đề từng từ" }[look.captions]);
  }
  if (look.title_text_style && look.title_text_style !== "same") words.push("Tiêu đề kiểu riêng");
  return words;
}

/** A line of text drawn with the look's colours, as the render draws the scenes' text box. */
function Sample({ look }: { look: Look }) {
  const drawn = palette(
    look.text_style ?? "yellow",
    look.text_color,
    look.box_color,
    look.accent_color,
    look.box_opacity,
  );
  const upper = (look.text_case ?? "upper") === "upper";
  const shadow = drawn.outline
    ? `-1px -1px 0 ${drawn.outline}, 1px -1px 0 ${drawn.outline}, -1px 1px 0 ${drawn.outline}, 1px 1px 0 ${drawn.outline}`
    : undefined;
  return (
    <div
      aria-hidden
      style={{
        background: "linear-gradient(135deg, #6b7a5a, #b9a27a)",
        borderRadius: 6,
        padding: "14px 10px",
        textAlign: "center",
      }}
    >
      <span
        style={{
          background: drawn.box ?? "transparent",
          color: drawn.text,
          textShadow: shadow,
          padding: "4px 8px",
          borderRadius: 4,
          fontWeight: 800,
          fontSize: 13,
          whiteSpace: "nowrap",
          textTransform: upper ? "uppercase" : "none",
        }}
      >
        Ngâm chân <span style={{ color: drawn.accent }}>nước ấm</span>
      </span>
    </div>
  );
}

/**
 * "Chữ & phụ đề của nhóm": the text look the group's new videos take over their maker's defaults (Cài đặt › Thiết lập
 * mặc định), "AI gợi ý" (a few looks for the group, one LLM call) and "AI chọn kiểu chữ cho từng video".
 */
export default function GroupTextLookCard({
  topic,
  start,
  update,
  reload,
}: {
  topic: KnowledgeTopic;
  /** Where a look of the group's own starts: the member's own defaults. */
  start: Look;
  update: Update;
  reload: (data?: Knowledge) => Promise<void>;
}) {
  const { message } = App.useApp();
  const [own, setOwn] = useState(topic.text_look !== null);
  const [look, setLook] = useState<Look>({ ...start, ...(topic.text_look ?? {}) });
  const [aiEach, setAiEach] = useState(topic.text_ai);
  const [seen, setSeen] = useState(JSON.stringify([topic.text_look, topic.text_ai]));
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  // A new saved value (another tab, "Lịch sử") replaces what the card shows.
  const key = JSON.stringify([topic.text_look, topic.text_ai]);
  if (seen !== key) {
    setSeen(key);
    setOwn(topic.text_look !== null);
    setLook({ ...start, ...(topic.text_look ?? {}) });
    setAiEach(topic.text_ai);
  }
  const making = topic.text_job?.status === "queued" || topic.text_job?.status === "running";
  const changed = !sameLook(own ? look : null, topic.text_look) || aiEach !== topic.text_ai;

  // Read the group again while its suggestions are being made, and stop once they are there (or failed).
  useEffect(() => {
    if (!making) return;
    const timer = window.setInterval(() => void reload().catch(() => undefined), POLL_MS);
    return () => window.clearInterval(timer);
  }, [making, reload]);

  async function save() {
    setBusy(true);
    try {
      await update({ text_look: own ? pick(look) : null, text_ai: aiEach });
      message.success("Đã lưu chữ & phụ đề của nhóm");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function suggest() {
    setAsking(true);
    try {
      await reload(await api<Knowledge>(`/knowledge/topics/${topic.id}/text-suggestions`, "POST"));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setAsking(false);
    }
  }

  const values: SettingsValues = { ...(start as VideoOptions), ...look, voice_enabled: true };
  return (
    <Card
      title="Chữ & phụ đề của nhóm"
      size="small"
      data-testid="group-text-look"
      extra={
        <EditHistory
          entityType="knowledge_topic"
          entityId={topic.id}
          field="text_look"
          title="Chữ & phụ đề của nhóm"
          kind="value"
          show={(saved) => (saved ? describe(saved as Look).join(", ") || "Kiểu riêng" : "Theo người tạo video")}
          current={topic.text_look ? describe(topic.text_look).join(", ") || "Kiểu riêng" : "Theo người tạo video"}
        />
      }
    >
      <Flex vertical gap={12}>
        <Typography.Text type="secondary">
          Kiểu hộp chữ, màu, cỡ chữ và phụ đề cho video mới của nhóm, thay cho Thiết lập mặc định của người tạo. Chỉnh
          riêng trên từng video vẫn được; video đã có không đổi.
        </Typography.Text>
        <Flex align="center" gap={8}>
          <Switch checked={own} onChange={setOwn} aria-label="Nhóm có kiểu chữ riêng" />
          {/* One fixed label, so the switch reads the same on and off (screen review 2026-11-12). */}
          <Typography.Text>Nhóm có kiểu chữ riêng</Typography.Text>
        </Flex>
        <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: -6 }}>
          {own
            ? "Bật: video mới của nhóm dùng kiểu chữ chỉnh bên dưới."
            : "Tắt: video mới theo Thiết lập mặc định của người tạo video."}
        </Typography.Text>
        <Flex align="center" gap={8}>
          <Switch checked={aiEach} onChange={setAiEach} aria-label="AI chọn kiểu chữ cho từng video" />
          <Typography.Text>AI chọn kiểu chữ cho từng video</Typography.Text>
        </Flex>
        {aiEach && (
          <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: -6 }}>
            Khi AI viết kịch bản, nó chọn luôn kiểu chữ hợp với nội dung video đó, đè lên kiểu của nhóm. Không tốn thêm
            lượt gọi AI. Video tự viết thì vẫn theo kiểu của nhóm.
          </Typography.Text>
        )}

        <Flex vertical gap={8} data-testid="text-suggestions">
          <Flex align="center" justify="space-between" gap={8} wrap>
            <Typography.Text strong>Gợi ý từ AI</Typography.Text>
            <Button icon={<BulbOutlined />} loading={asking} disabled={making} onClick={() => void suggest()}>
              {topic.text_suggestions ? "Gợi ý lại" : "AI gợi ý"}
            </Button>
          </Flex>
          {making ? (
            <Flex align="center" gap={8}>
              <Spin size="small" />
              <Typography.Text type="secondary">
                AI đang nghĩ kiểu chữ cho nhóm (vài giây, dùng AI của nhóm)…
              </Typography.Text>
            </Flex>
          ) : topic.text_job?.status === "failed" ? (
            <Alert type="error" showIcon message="AI chưa gợi ý được" description={topic.text_job.error} />
          ) : null}
          {!making && !topic.text_suggestions && topic.text_job === null && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              AI đọc tên, prompt và gợi ý ảnh của nhóm rồi đề xuất vài phong cách chữ khác nhau. Mỗi lần là một lượt gọi
              AI của nhóm.
            </Typography.Text>
          )}
          {topic.text_suggestions?.options.map((option, index) => (
            <Card key={`${topic.text_suggestions!.job_id}-${index}`} size="small" data-testid="text-suggestion">
              <Flex gap={12} align="center" wrap>
                <div style={{ flex: "0 0 180px" }}>
                  <Sample look={option.look} />
                </div>
                <Flex vertical gap={4} style={{ flex: "1 1 200px", minWidth: 0 }}>
                  <Typography.Text strong>{option.name}</Typography.Text>
                  {option.reason && (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {option.reason}
                    </Typography.Text>
                  )}
                  <Flex gap={4} wrap>
                    {describe(option.look).map((word) => (
                      <Tag key={word}>{word}</Tag>
                    ))}
                  </Flex>
                </Flex>
                <Button
                  onClick={() => {
                    setOwn(true);
                    setLook({ ...start, ...(topic.text_look ?? {}), ...option.look });
                    message.info("Đã đưa vào phần chỉnh bên dưới, bấm “Lưu chữ & phụ đề” để dùng");
                  }}
                >
                  Dùng kiểu này
                </Button>
              </Flex>
            </Card>
          ))}
        </Flex>

        {own && (
          <TextSettings values={values} onChange={(changes) => setLook((current) => ({ ...current, ...changes }))} />
        )}
        <Button
          type="primary"
          loading={busy}
          disabled={!changed}
          onClick={() => void save()}
          style={{ alignSelf: "start" }}
        >
          Lưu chữ & phụ đề
        </Button>
      </Flex>
    </Card>
  );
}
