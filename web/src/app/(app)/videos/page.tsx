"use client";

import { AppstoreOutlined, PlusOutlined, SearchOutlined, UnorderedListOutlined } from "@ant-design/icons";
import {
  App,
  Button,
  Card,
  Col,
  Empty,
  Flex,
  Form,
  Input,
  Modal,
  Row,
  Segmented,
  Select,
  Spin,
  Table,
  Typography,
} from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useMe } from "@/components/MeContext";
import VideoStatusTags from "@/components/VideoStatusTags";
import VideoThumbnail from "@/components/VideoThumbnail";
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
import PageHeader from "@/components/PageHeader";
import { usePolling } from "@/lib/polling";
import { useRememberedView, type View } from "@/lib/view";

const REFRESH_MS = 5000;
const VIEW_KEY = "reels-studio.videos-view";

type StatusFilter = "all" | "draft" | "working" | "done" | "failed" | "outdated";

/** The status filter's groups: a job in any stage counts as "Đang xử lý". */
const STATUS_FILTERS: { value: StatusFilter; label: string; match: (row: VideoRow) => boolean }[] = [
  { value: "all", label: "Mọi trạng thái", match: () => true },
  { value: "draft", label: "Nháp", match: (row) => row.status === "draft" },
  {
    value: "working",
    label: "Đang xử lý",
    match: (row) => !["draft", "done", "failed"].includes(row.status),
  },
  { value: "done", label: "Xong", match: (row) => row.status === "done" },
  { value: "failed", label: "Lỗi", match: (row) => row.status === "failed" || row.rerender_failed },
  { value: "outdated", label: "MP4 cần render lại", match: (row) => row.mp4_outdated },
];

export default function VideosPage() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<VideoRow[] | null>(null);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const { me } = useMe();
  const [status, setStatus] = useState<StatusFilter>("all");
  const [mine, setMine] = useState(false);
  const [view, chooseView] = useRememberedView(VIEW_KEY);

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
    return () => clearTimeout(timer);
  }, [query, reload]);
  // Statuses change in the worker: keep the list current without a reload.
  usePolling(() => reload(query, true), REFRESH_MS);

  const match = STATUS_FILTERS.find((item) => item.value === status)!.match;
  const shown = (rows ?? []).filter((row) => match(row) && (!mine || row.created_by === me.name));
  const filtered = Boolean(query.trim()) || status !== "all" || mine;

  return (
    <>
      <PageHeader
        title="Video"
        actions={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
            Tạo video
          </Button>
        }
      >
        <Input
          aria-label="Tìm theo tiêu đề hoặc chủ đề"
          prefix={<SearchOutlined />}
          placeholder="Tìm theo tiêu đề hoặc chủ đề"
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ width: 320, maxWidth: "100%" }}
        />
        <Select
          aria-label="Lọc theo trạng thái"
          value={status}
          onChange={setStatus}
          options={STATUS_FILTERS.map(({ value, label }) => ({ value, label }))}
          style={{ width: 190 }}
        />
        <Segmented
          aria-label="Người tạo"
          value={mine ? "mine" : "all"}
          onChange={(value) => setMine(value === "mine")}
          options={[
            { value: "all", label: "Cả đội" },
            { value: "mine", label: "Của tôi" },
          ]}
        />
        <Segmented
          aria-label="Kiểu hiển thị"
          value={view}
          onChange={(value) => chooseView(value as View)}
          style={{ marginLeft: "auto" }}
          options={[
            { value: "grid", icon: <AppstoreOutlined />, title: "Dạng lưới" },
            { value: "list", icon: <UnorderedListOutlined />, title: "Dạng danh sách" },
          ]}
        />
      </PageHeader>
      {rows === null ? (
        <Flex justify="center" style={{ padding: 48 }}>
          <Spin />
        </Flex>
      ) : shown.length === 0 ? (
        <Card>
          <Empty description={filtered ? "Không có video nào khớp" : "Chưa có video nào"} />
        </Card>
      ) : view === "grid" ? (
        <Row gutter={[16, 16]}>
          {shown.map((row) => (
            <Col key={row.id} xs={12} sm={8} md={6} xl={4} style={{ display: "flex" }}>
              <VideoCard row={row} />
            </Col>
          ))}
        </Row>
      ) : (
        <VideoTable rows={shown} />
      )}
      <NewVideoModal open={creating} onClose={() => setCreating(false)} />
    </>
  );
}

function VideoCard({ row }: { row: VideoRow }) {
  const name = row.title || row.topic;
  return (
    <Link
      prefetch={false}
      href={`/videos/${row.id}`}
      aria-label={name}
      data-testid="video-card"
      style={{ display: "flex", flex: 1 }}
    >
      {/* Every card in a row is as tall as the tallest, and its date sits at the bottom. */}
      <Card
        hoverable
        style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}
        styles={{ body: { padding: 12, flex: 1, display: "flex", flexDirection: "column", gap: 6 } }}
        cover={<VideoThumbnail name={name} url={row.thumbnail_url} />}
      >
        <Typography.Paragraph strong ellipsis={{ rows: 2 }} style={{ margin: 0 }}>
          {name}
        </Typography.Paragraph>
        <VideoStatusTags video={row} />
        <Typography.Text type="secondary" style={{ marginTop: "auto", fontSize: 12 }}>
          {row.created_by} · {formatDateTime(row.created_at)}
        </Typography.Text>
      </Card>
    </Link>
  );
}

/** "Dạng danh sách": one row per video, to scan many at once. */
function VideoTable({ rows }: { rows: VideoRow[] }) {
  const router = useRouter();
  return (
    <Card styles={{ body: { padding: 0 } }}>
      <Table<VideoRow>
        rowKey="id"
        dataSource={rows}
        pagination={{ pageSize: 50, hideOnSinglePage: true }}
        scroll={{ x: 760 }}
        onRow={(row) => ({
          onClick: () => router.push(`/videos/${row.id}`),
          style: { cursor: "pointer" },
          "data-testid": "video-row",
        })}
        columns={[
          {
            title: "Video",
            key: "video",
            render: (_, row) => (
              <Flex align="center" gap={12}>
                <VideoThumbnail name={row.title || row.topic} url={row.thumbnail_url} width={36} />
                <Flex vertical style={{ minWidth: 0 }}>
                  <Link prefetch={false} href={`/videos/${row.id}`} onClick={(event) => event.stopPropagation()}>
                    <Typography.Text strong ellipsis style={{ maxWidth: 520 }}>
                      {row.title || row.topic}
                    </Typography.Text>
                  </Link>
                  {row.title && (
                    <Typography.Text type="secondary" ellipsis style={{ maxWidth: 520, fontSize: 12 }}>
                      Chủ đề: {row.topic}
                    </Typography.Text>
                  )}
                </Flex>
              </Flex>
            ),
          },
          { title: "Trạng thái", key: "status", width: 260, render: (_, row) => <VideoStatusTags video={row} /> },
          { title: "Người tạo", dataIndex: "created_by", width: 160 },
          { title: "Ngày tạo", key: "created", width: 160, render: (_, row) => formatDateTime(row.created_at) },
        ]}
      />
    </Card>
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
                  {llm.problem}.{" "}
                  <Link prefetch={false} href="/settings/ai">
                    Mở Cài đặt › Mô hình AI
                  </Link>
                </>
              ) : (
                <>
                  Viết bằng: {llm.name} · {llm.model} (
                  <Link prefetch={false} href="/settings/ai">
                    đổi trong Cài đặt
                  </Link>
                  )
                </>
              )}
            </Typography.Paragraph>
          )}
        </Form>
      )}
    </Modal>
  );
}
