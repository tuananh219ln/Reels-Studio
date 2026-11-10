"use client";

import { InboxOutlined } from "@ant-design/icons";
import { Alert, Form, Input, Segmented, Select, Typography, Upload, type UploadFile } from "antd";
import type { SampleMode, SampleSummary } from "@/lib/api";

/** The ways of "Từ video mẫu" (api reference.MODES), each with what it does, shown under the choice. */
export const SAMPLE_MODES: { value: SampleMode; label: string; description: string }[] = [
  {
    value: "quick",
    label: "Nhanh",
    description: "AI xem video mẫu một lần rồi viết luôn kịch bản và chọn đoạn clip cho từng cảnh. Nhanh và rẻ nhất.",
  },
  {
    value: "twostep",
    label: "Hai bước tự động",
    description:
      "AI phân tích video mẫu trước, rồi viết kịch bản dựa trên bản phân tích. Bước viết không nhìn lại hình nên việc chọn clip dựa vào mô tả khung hình.",
  },
  {
    value: "review",
    label: "Duyệt phân tích trước",
    description:
      "AI phân tích video mẫu, bạn đọc và sửa bản phân tích, rồi bấm “Viết kịch bản”. Kiểm soát tốt nhất, phải chờ hai lần.",
  },
  {
    value: "reuse",
    label: "Dùng mẫu đã học",
    description:
      "Chọn một video mẫu đã phân tích trước đó để viết video mới với chủ đề khác. Không tải lại, không phân tích lại.",
  },
  {
    value: "footage",
    label: "Edit từ footage",
    description:
      "Đưa clip bạn tự quay (nói trước camera, review sản phẩm). App tách lời, bỏ khoảng lặng và tiếng “ờ, à”, chia thành cảnh giữ nguyên tiếng gốc, phụ đề chạy theo đúng lời nói. Không gọi AI viết kịch bản; cần key ElevenLabs có quyền Speech to Text.",
  },
];

/** api remote_media.MAX_SAMPLE_BYTES; the api checks it again, and the 3 minutes, which only the file can tell. */
const MAX_SAMPLE_MB = 100;

export type SampleSource = "link" | "file";

export type SampleValues = {
  sample_mode: SampleMode;
  sample_source: SampleSource;
  sample_url?: string;
  sample_file?: UploadFile[];
  reference_id?: number;
};

export function sampleLength(seconds: number | null): string {
  if (seconds === null) {
    return "";
  }
  const whole = Math.round(seconds);
  return whole >= 60 ? `${Math.floor(whole / 60)} phút ${whole % 60} giây` : `${whole} giây`;
}

function sampleLabel(sample: SampleSummary): string {
  const parts = [sample.source_name, sampleLength(sample.seconds), `${sample.video_count} video`];
  return parts.filter(Boolean).join(", ");
}

/** The fields of "Từ video mẫu" in the "Tạo video" drawer; they live in its Form, so it reads them on submit. */
export default function SampleFields({ samples }: { samples: SampleSummary[] | null }) {
  const form = Form.useFormInstance<SampleValues>();
  const mode: SampleMode = Form.useWatch("sample_mode", form) ?? "quick";
  const source: SampleSource = Form.useWatch("sample_source", form) ?? "link";
  const referenceId = Form.useWatch("reference_id", form);
  const chosen = samples?.find((sample) => sample.id === referenceId);
  const way = SAMPLE_MODES.find((item) => item.value === mode)!;

  return (
    <>
      <Form.Item
        label="Cách làm"
        name="sample_mode"
        extra={<span data-testid="sample-mode-help">{way.description}</span>}
      >
        <Select
          aria-label="Cách làm"
          options={SAMPLE_MODES.map(({ value, label }) => ({ value, label }))}
          style={{ maxWidth: 320 }}
        />
      </Form.Item>
      {mode === "reuse" ? (
        samples !== null && samples.length === 0 ? (
          <Alert
            type="info"
            style={{ marginBottom: 16 }}
            title="Chưa có video mẫu nào. Hãy chọn cách làm khác để dán link hoặc tải video mẫu lên."
          />
        ) : (
          <>
            <Form.Item
              label="Video mẫu đã học"
              name="reference_id"
              rules={[{ required: true, message: "Hãy chọn một video mẫu đã học" }]}
            >
              <Select
                aria-label="Video mẫu đã học"
                loading={samples === null}
                showSearch={{ optionFilterProp: "label" }}
                options={(samples ?? []).map((sample) => ({ value: sample.id, label: sampleLabel(sample) }))}
              />
            </Form.Item>
            {chosen && (
              <div style={{ marginTop: -8, marginBottom: 16 }} data-testid="chosen-sample">
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {chosen.analyzed ? "Bản phân tích:" : "Mẫu này chưa được phân tích; AI sẽ phân tích trước khi viết."}
                </Typography.Text>
                {chosen.analyzed && (
                  <Typography.Paragraph
                    type="secondary"
                    ellipsis={{ rows: 4, expandable: "collapsible", symbol: (open) => (open ? "Thu gọn" : "Xem thêm") }}
                    style={{ whiteSpace: "pre-wrap", fontSize: 13, margin: 0 }}
                  >
                    {chosen.analysis}
                  </Typography.Paragraph>
                )}
              </div>
            )}
          </>
        )
      ) : (
        <>
          <Form.Item
            label={mode === "footage" ? "Footage" : "Video mẫu"}
            name="sample_source"
            style={{ marginBottom: 8 }}
          >
            <Segmented
              aria-label="Nguồn video mẫu"
              options={[
                { value: "link", label: "Dán link" },
                { value: "file", label: "Tải video lên" },
              ]}
            />
          </Form.Item>
          {source === "link" ? (
            <Form.Item
              name="sample_url"
              rules={[{ required: true, whitespace: true, message: "Hãy dán link video mẫu" }]}
              extra="Link TikTok, YouTube Shorts hoặc link file MP4. Video dài tối đa 3 phút."
            >
              <Input aria-label="Link video mẫu" placeholder="https://www.tiktok.com/@kenh/video/…" allowClear />
            </Form.Item>
          ) : (
            <Form.Item
              name="sample_file"
              valuePropName="fileList"
              getValueFromEvent={(event: { fileList: UploadFile[] }) => event.fileList.slice(-1)}
              rules={[
                { required: true, message: "Hãy chọn file video mẫu" },
                {
                  validator: async (_, files?: UploadFile[]) => {
                    const size = files?.[0]?.size ?? 0;
                    if (size > MAX_SAMPLE_MB * 1024 * 1024) {
                      throw new Error(`Video mẫu quá ${MAX_SAMPLE_MB} MB, hãy chọn video ngắn hơn`);
                    }
                  },
                },
              ]}
              extra={`MP4, MOV hoặc WebM, tối đa ${MAX_SAMPLE_MB} MB và 3 phút.`}
            >
              <Upload.Dragger
                accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm"
                maxCount={1}
                beforeUpload={() => false}
                aria-label="Tải video mẫu lên"
              >
                <p className="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p className="ant-upload-text">Kéo video vào đây hoặc bấm để chọn file</p>
              </Upload.Dragger>
            </Form.Item>
          )}
        </>
      )}
    </>
  );
}
