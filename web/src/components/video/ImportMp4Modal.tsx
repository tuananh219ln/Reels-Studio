"use client";

import { InboxOutlined } from "@ant-design/icons";
import { Alert, App, Flex, Form, Input, Modal, Progress, Select, Typography, Upload } from "antd";
import type { UploadFile } from "antd";
import { useEffect, useState } from "react";
import {
  api,
  errorMessage,
  uploadWithProgress,
  type Knowledge,
  type Plan,
  type PlanItem,
  type VideoDetail,
} from "@/lib/api";

const MAX_MB = 200;

type Values = {
  file: UploadFile[];
  knowledge_topic_id?: number;
  plan_item_id?: number;
  title?: string;
  caption?: string;
  hashtags?: string;
};

/** "Import MP4": a finished MP4 becomes a video as it is (no render). From an idea's "Import MP4" the group and the
 * idea are fixed; from the Video list the member picks the group and, optionally, an idea that has no video yet. With
 * `replaceVideoId` it swaps the MP4 of an upload video that is not posted yet ("Thay MP4"). */
export default function ImportMp4Modal({
  open,
  onClose,
  onDone,
  topicId,
  planItem,
  replaceVideoId,
}: {
  open: boolean;
  onClose: () => void;
  onDone: (video: VideoDetail) => void;
  topicId?: number;
  planItem?: Pick<PlanItem, "id" | "topic">;
  replaceVideoId?: number;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm<Values>();
  const [topics, setTopics] = useState<Knowledge["topics"]>([]);
  const [ideas, setIdeas] = useState<{ group: number; items: PlanItem[] } | null>(null);
  const [percent, setPercent] = useState<number | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const group = Form.useWatch("knowledge_topic_id", form) ?? topicId;
  const replacing = replaceVideoId !== undefined;

  useEffect(() => {
    if (!open || topicId !== undefined || replacing) return;
    api<Knowledge>("/knowledge")
      .then((knowledge) => setTopics(knowledge.topics))
      .catch((err) => message.error(errorMessage(err)));
  }, [open, topicId, replacing, message]);

  useEffect(() => {
    if (!open || replacing || planItem || !group) return;
    api<Plan>(`/plans/${group}`)
      .then((plan) => setIdeas({ group, items: plan.items.filter((item) => item.video_id === null) }))
      .catch(() => setIdeas(null));
  }, [open, group, planItem, replacing]);
  // Only the picked group's ideas: a slower answer for an earlier pick is never shown.
  const free = ideas && ideas.group === group ? ideas.items : [];

  async function submit(values: Values) {
    const file = values.file?.[0]?.originFileObj;
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    setFailure(null);
    setPercent(0);
    try {
      let video: VideoDetail;
      if (replacing) {
        video = await uploadWithProgress<VideoDetail>(`/videos/${replaceVideoId}/source-mp4`, "PUT", form, setPercent);
      } else {
        form.append("knowledge_topic_id", String(topicId ?? values.knowledge_topic_id));
        const idea = planItem?.id ?? values.plan_item_id;
        if (idea) form.append("plan_item_id", String(idea));
        form.append("title", values.title?.trim() || planItem?.topic || "");
        form.append("caption", values.caption ?? "");
        form.append("hashtags", values.hashtags ?? "");
        video = await uploadWithProgress<VideoDetail>("/videos/upload", "POST", form, setPercent);
      }
      message.success(replacing ? "Đã thay MP4, video quay về Chờ duyệt" : "Đã tạo video từ MP4");
      onDone(video);
    } catch (err) {
      setFailure(errorMessage(err));
    } finally {
      setPercent(null);
    }
  }

  return (
    <Modal
      title={replacing ? "Thay MP4" : "Import MP4"}
      open={open}
      onCancel={percent === null ? onClose : undefined}
      onOk={() => form.submit()}
      okText={replacing ? "Thay MP4" : "Tạo video"}
      cancelText="Huỷ"
      confirmLoading={percent !== null}
      destroyOnHidden
      afterClose={() => {
        form.resetFields();
        setFailure(null);
      }}
    >
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={submit}
        initialValues={{ title: planItem?.topic }}
      >
        <Typography.Paragraph type="secondary">
          {replacing
            ? "File mới thay file cũ; caption, hashtag và ý tưởng giữ nguyên. Video cần được duyệt lại."
            : `File MP4 đã dựng xong (tối đa ${MAX_MB} MB) được dùng nguyên để đăng, Studio không dựng lại.`}
        </Typography.Paragraph>
        {failure && (
          <Alert type="error" showIcon message={failure} style={{ marginBottom: 12 }} data-testid="import-mp4-error" />
        )}
        <Form.Item
          name="file"
          valuePropName="fileList"
          getValueFromEvent={(event: { fileList: UploadFile[] }) => event.fileList.slice(-1)}
          rules={[{ required: true, message: "Hãy chọn file MP4" }]}
        >
          <Upload.Dragger
            accept=".mp4,.mov,video/mp4,video/quicktime"
            maxCount={1}
            beforeUpload={(file) => {
              if (file.size > MAX_MB * 1024 * 1024) {
                message.error(`File quá ${MAX_MB} MB, hãy nén nhỏ hơn`);
                return Upload.LIST_IGNORE;
              }
              return false; // sent by "Tạo video", with its progress
            }}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">Kéo thả file MP4 vào đây hoặc bấm để chọn</p>
          </Upload.Dragger>
        </Form.Item>
        {!replacing && topicId === undefined && (
          <Form.Item
            name="knowledge_topic_id"
            label="Nhóm chủ đề"
            rules={[{ required: true, message: "Hãy chọn nhóm" }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              placeholder="Chọn nhóm"
              options={topics.map((topic) => ({ value: topic.id, label: topic.name }))}
              onChange={() => form.setFieldValue("plan_item_id", undefined)}
            />
          </Form.Item>
        )}
        {!replacing && !planItem && (
          <Form.Item name="plan_item_id" label="Ý tưởng kế hoạch (không bắt buộc)">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="Không chọn: video lẻ ngoài kế hoạch"
              disabled={!group}
              options={free.map((item) => ({
                value: item.id,
                label: `${item.day === null ? "Backlog" : `Ngày ${item.day}`}: ${item.topic}`,
              }))}
              onChange={(id: number | undefined) => {
                const idea = free.find((item) => item.id === id);
                if (idea && !form.getFieldValue("title")) form.setFieldValue("title", idea.topic);
              }}
            />
          </Form.Item>
        )}
        {!replacing && (
          <>
            <Form.Item name="title" label="Tiêu đề">
              <Input maxLength={200} placeholder="Để trống: lấy theo ý tưởng hoặc tên file" />
            </Form.Item>
            <Form.Item name="caption" label="Caption">
              <Input.TextArea rows={3} maxLength={5000} />
            </Form.Item>
            <Form.Item name="hashtags" label="Hashtag" extra="Cách nhau bằng dấu cách hoặc dấu phẩy">
              <Input placeholder="#healthtips #SeniorHealth" />
            </Form.Item>
          </>
        )}
        {percent !== null && (
          <Flex vertical gap={4}>
            <Progress percent={percent} status="active" />
            <Typography.Text type="secondary">
              {percent < 100 ? "Đang tải lên…" : "Đang kiểm tra file…"}
            </Typography.Text>
          </Flex>
        )}
      </Form>
    </Modal>
  );
}
