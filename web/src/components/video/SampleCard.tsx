"use client";

import { useMe } from "@/components/MeContext";
import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { App, Button, Card, Collapse, Flex, Input, Typography, theme } from "antd";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, errorMessage, type VideoDetail, type VideoSample } from "@/lib/api";
import { sampleLength } from "./SampleFields";

/** api reference.MAX_ANALYSIS_LENGTH. */
const MAX_ANALYSIS = 8000;

/** "Video mẫu" on a video made from a sample video: where it came from, the AI's analysis, the words and stills.
 * In the way "Duyệt phân tích trước" the analysis is edited here, then "Viết kịch bản" writes from it. */
export default function SampleCard({
  sample,
  videoId,
  hasScript,
  working,
  onVideo,
  onChanged,
}: {
  sample: VideoSample;
  videoId: number;
  hasScript: boolean;
  /** A job runs on the video: nothing here can be changed until it is done. */
  working: boolean;
  onVideo: (video: VideoDetail) => void;
  /** Reload the video after a change that does not return it (the sample deleted). */
  onChanged: () => void;
}) {
  const { message, modal } = App.useApp();
  const { me } = useMe();
  const { token } = theme.useToken();
  const router = useRouter();
  const [draft, setDraft] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const reviewing = sample.awaiting_review && !working && sample.id !== null;
  const text = draft ?? sample.analysis;

  async function saveAnalysis(): Promise<boolean> {
    if (text.trim() === sample.analysis.trim()) {
      return true;
    }
    await api(`/references/${sample.id}`, "PATCH", { analysis: text });
    setDraft(null);
    return true;
  }

  async function save(thenWrite: boolean) {
    setBusy(true);
    try {
      await saveAnalysis();
      if (thenWrite) {
        onVideo(await api<VideoDetail>(`/videos/${videoId}/script`, "POST"));
      } else {
        message.success("Đã lưu bản phân tích");
        onChanged();
      }
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function remove() {
    modal.confirm({
      title: "Xoá video mẫu?",
      content:
        "File video mẫu, khung hình và bản phân tích bị xoá. Các video đã làm từ mẫu này vẫn giữ kịch bản và clip của chúng.",
      okText: "Xoá",
      okButtonProps: { danger: true },
      cancelText: "Huỷ",
      onOk: async () => {
        try {
          await api(`/references/${sample.id}`, "DELETE");
          message.success("Đã xoá video mẫu");
          onChanged();
        } catch (err) {
          message.error(errorMessage(err));
        }
      },
    });
  }

  const source =
    sample.id === null ? (
      <Typography.Text type="secondary">Video mẫu đã bị xoá; kịch bản và clip của video này vẫn còn.</Typography.Text>
    ) : (
      <Typography.Text type="secondary" style={{ fontSize: 13 }}>
        {sample.source_url ? (
          <a href={sample.source_url} target="_blank" rel="noreferrer" style={{ wordBreak: "break-all" }}>
            {sample.source_name}
          </a>
        ) : (
          <>File tải lên: {sample.source_name}</>
        )}
        {sample.seconds !== null && `, ${sampleLength(sample.seconds)}`}, cách làm: {sample.mode_label}
      </Typography.Text>
    );

  const analysis = reviewing ? (
    <div data-testid="sample-review">
      <Typography.Paragraph style={{ marginBottom: 8 }}>
        AI đã phân tích xong video mẫu. Đọc và sửa bản phân tích (VD: “giữ hook, bỏ đoạn cuối”), rồi bấm “Viết kịch
        bản”: kịch bản được viết theo bản phân tích này.
      </Typography.Paragraph>
      <Input.TextArea
        aria-label="Bản phân tích video mẫu"
        value={text}
        maxLength={MAX_ANALYSIS}
        autoSize={{ minRows: 8, maxRows: 24 }}
        onChange={(event) => setDraft(event.target.value)}
      />
      <Flex gap={8} wrap style={{ marginTop: 12 }}>
        <Button
          type="primary"
          icon={<EditOutlined />}
          loading={busy}
          disabled={!text.trim()}
          onClick={() => save(true)}
        >
          Viết kịch bản
        </Button>
        <Button disabled={busy || !text.trim() || draft === null} onClick={() => save(false)}>
          Lưu phân tích
        </Button>
      </Flex>
    </div>
  ) : sample.analysis ? (
    <Typography.Paragraph style={{ whiteSpace: "pre-wrap", margin: 0 }} data-testid="sample-analysis">
      {sample.analysis}
    </Typography.Paragraph>
  ) : (
    <Typography.Text type="secondary">{working ? "AI đang xem video mẫu…" : "Chưa có bản phân tích."}</Typography.Text>
  );

  const details = (
    <Flex vertical gap={12}>
      <div>
        <Typography.Text strong>Phân tích của AI</Typography.Text>
        <div style={{ marginTop: 4 }}>{analysis}</div>
      </div>
      {sample.frames.length > 0 && (
        <div>
          <Typography.Text strong>Khung hình</Typography.Text>
          <Flex gap={8} style={{ overflowX: "auto", paddingBottom: 4, marginTop: 4 }} data-testid="sample-frames">
            {sample.frames.map((frame) => (
              <figure
                key={frame.url}
                style={{ margin: 0, flex: "0 0 auto", width: 72 }}
                title={frame.note || undefined}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- served by the api behind the session cookie */}
                <img
                  src={frame.url}
                  alt={frame.note || `Khung giây ${frame.second}`}
                  style={{
                    width: 72,
                    height: 128,
                    objectFit: "cover",
                    borderRadius: token.borderRadiusSM,
                    background: token.colorFillTertiary,
                  }}
                />
                <figcaption style={{ fontSize: 12, color: token.colorTextSecondary, textAlign: "center" }}>
                  {Math.round(frame.second)} giây
                </figcaption>
              </figure>
            ))}
          </Flex>
        </div>
      )}
      {sample.transcript && (
        <Collapse
          size="small"
          items={[
            {
              key: "words",
              label: "Lời thoại video mẫu",
              children: (
                <Typography.Paragraph style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: 13 }}>
                  {sample.transcript}
                </Typography.Paragraph>
              ),
            },
          ]}
        />
      )}
    </Flex>
  );

  return (
    <Card
      size="small"
      title="Video mẫu"
      style={{ marginBottom: 16 }}
      data-testid="sample-card"
      extra={
        sample.id !== null && (
          <Flex gap={4} wrap>
            {sample.analysis && (
              <Button
                size="small"
                type="text"
                icon={<PlusOutlined />}
                onClick={() => router.push(`/videos?reference=${sample.id}`)}
              >
                Tạo thêm video từ mẫu này
              </Button>
            )}
            {sample.created_by_id === me.id && (
              <Button
                size="small"
                type="text"
                danger
                icon={<DeleteOutlined />}
                disabled={working}
                onClick={remove}
                aria-label="Xoá video mẫu"
              />
            )}
          </Flex>
        )
      }
    >
      {source}
      {sample.id !== null && (
        <div style={{ marginTop: 12 }}>
          {/* Once the script is written the details are for looking back at, so they start folded. */}
          {hasScript ? (
            <Collapse
              ghost
              size="small"
              items={[{ key: "details", label: "Xem phân tích, khung hình và lời thoại", children: details }]}
            />
          ) : (
            details
          )}
        </div>
      )}
    </Card>
  );
}
