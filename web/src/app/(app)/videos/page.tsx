"use client";

import { PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { App, Button, Card, Col, Empty, Flex, Form, Input, Modal, Row, Select, Spin, Typography } from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import VideoStatusTags from "@/components/VideoStatusTags";
import {
  api,
  errorMessage,
  formatDateTime,
  type ActiveLlm,
  type Knowledge,
  type KnowledgeTopic,
  type VideoDetail,
  type VideoRow,
} from "@/lib/api";

const REFRESH_MS = 5000;

export default function VideosPage() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<VideoRow[] | null>(null);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);

  const reload = useCallback(
    async (q: string, quiet = false) => {
      try {
        setRows(await api<VideoRow[]>(`/videos?q=${encodeURIComponent(q)}`));
      } catch (err) {
        if (!quiet) {
          message.error(errorMessage(err));
        }
      }
    },
    [message],
  );

  useEffect(() => {
    const timer = setTimeout(() => reload(query), 250);
    // Statuses change in the worker: keep the list current without a reload.
    const refresh = setInterval(() => reload(query, true), REFRESH_MS);
    return () => {
      clearTimeout(timer);
      clearInterval(refresh);
    };
  }, [query, reload]);

  return (
    <>
      <Typography.Title level={2} style={{ marginTop: 0, fontWeight: 600 }}>
        Video
      </Typography.Title>
      <Flex wrap gap={12} justify="space-between" style={{ marginBottom: 16 }}>
        <Input
          aria-label="Tìm theo tiêu đề hoặc chủ đề"
          prefix={<SearchOutlined />}
          placeholder="Tìm theo tiêu đề hoặc chủ đề"
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ maxWidth: 320 }}
        />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
          Tạo video
        </Button>
      </Flex>
      {rows === null ? (
        <Flex justify="center" style={{ padding: 48 }}>
          <Spin />
        </Flex>
      ) : rows.length === 0 ? (
        <Card>
          <Empty description={query.trim() ? "Không có video nào khớp" : "Chưa có video nào"} />
        </Card>
      ) : (
        <Row gutter={[16, 16]}>
          {rows.map((row) => (
            <Col key={row.id} xs={12} sm={8} md={6} xl={4}>
              <VideoCard row={row} />
            </Col>
          ))}
        </Row>
      )}
      <NewVideoModal open={creating} onClose={() => setCreating(false)} />
    </>
  );
}

function VideoCard({ row }: { row: VideoRow }) {
  const name = row.title || row.topic;
  return (
    <Link href={`/videos/${row.id}`} aria-label={name} data-testid="video-card">
      <Card
        hoverable
        styles={{ body: { padding: 12 } }}
        cover={
          row.thumbnail_url ? (
            // A plain <img>: thumbnails come from the api behind the session cookie, which next/image's
            // optimizer would not send.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={row.thumbnail_url} alt={name} style={{ aspectRatio: "9 / 16", objectFit: "cover" }} />
          ) : (
            <Flex
              align="center"
              justify="center"
              style={{ aspectRatio: "9 / 16", background: "#E4E4E4", padding: 12, textAlign: "center" }}
            >
              <Typography.Text type="secondary">{name}</Typography.Text>
            </Flex>
          )
        }
      >
        <Typography.Paragraph strong ellipsis={{ rows: 2 }} style={{ marginBottom: 6 }}>
          {name}
        </Typography.Paragraph>
        <VideoStatusTags video={row} />
        <Typography.Paragraph type="secondary" style={{ margin: "6px 0 0", fontSize: 12 }}>
          {row.created_by} · {formatDateTime(row.created_at)}
        </Typography.Paragraph>
      </Card>
    </Link>
  );
}

type NewVideo = { topic: string; knowledge_topic_id: number };

function NewVideoModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { message } = App.useApp();
  const router = useRouter();
  const [form] = Form.useForm<NewVideo>();
  const [busy, setBusy] = useState(false);
  const [topics, setTopics] = useState<KnowledgeTopic[] | null>(null);
  const [llm, setLlm] = useState<ActiveLlm | null>(null);

  useEffect(() => {
    if (open) {
      api<Knowledge>("/knowledge")
        .then((data) => setTopics(data.topics))
        .catch((err) => message.error(errorMessage(err)));
      // Only informative: a failure here leaves the line out and never blocks creating the video.
      api<ActiveLlm>("/settings/llm/active")
        .then(setLlm)
        .catch(() => setLlm(null));
    }
  }, [open, message]);

  async function submit(values: NewVideo) {
    setBusy(true);
    try {
      const video = await api<VideoDetail>("/videos", "POST", values);
      router.push(`/videos/${video.id}`);
    } catch (err) {
      message.error(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Tạo video"
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      okText="Viết kịch bản"
      cancelText="Huỷ"
      confirmLoading={busy}
      destroyOnHidden
    >
      {topics === null ? (
        <Flex justify="center" style={{ padding: 24 }}>
          <Spin />
        </Flex>
      ) : (
        <Form
          form={form}
          layout="vertical"
          requiredMark={false}
          onFinish={submit}
          initialValues={{ knowledge_topic_id: topics.find((topic) => topic.script_prompt)?.id }}
        >
          <Form.Item
            label="Nhóm chủ đề"
            name="knowledge_topic_id"
            rules={[{ required: true, message: "Hãy chọn nhóm chủ đề" }]}
            extra="Quyết định prompt và từ cấm dùng cho video, sửa trong Kho kiến thức"
          >
            <Select
              options={topics.map((topic) => ({
                value: topic.id,
                label: topic.script_prompt ? topic.name : `${topic.name} (chưa có prompt)`,
                disabled: !topic.script_prompt,
              }))}
            />
          </Form.Item>
          <Form.Item
            label="Chủ đề"
            name="topic"
            rules={[{ required: true, whitespace: true, message: "Hãy nhập chủ đề" }]}
            extra="VD: thực phẩm tốt cho xương khớp người sau 50 tuổi"
          >
            <Input.TextArea autoSize={{ minRows: 2, maxRows: 4 }} maxLength={300} />
          </Form.Item>
          {llm && (
            <Typography.Paragraph
              type={llm.problem ? "danger" : "secondary"}
              style={{ margin: 0 }}
              data-testid="llm-line"
            >
              {llm.problem ? (
                <>
                  {llm.problem}. <Link href="/settings/ai">Mở Cài đặt › Mô hình AI</Link>
                </>
              ) : (
                <>
                  Viết bằng: {llm.name} · {llm.model} (<Link href="/settings/ai">đổi trong Cài đặt</Link>)
                </>
              )}
            </Typography.Paragraph>
          )}
        </Form>
      )}
    </Modal>
  );
}
