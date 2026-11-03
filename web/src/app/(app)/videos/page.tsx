"use client";

import { AppstoreOutlined, PlusOutlined, SearchOutlined, UnorderedListOutlined } from "@ant-design/icons";
import {
  Alert,
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
  Tag,
  Typography,
} from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useMe } from "@/components/MeContext";
import VideoStatusTags from "@/components/VideoStatusTags";
import VideoThumbnail from "@/components/VideoThumbnail";
import VideoTitleCell from "@/components/VideoTitleCell";
import {
  api,
  errorMessage,
  formatDateTime,
  type ActiveLlm,
  type Knowledge,
  type KnowledgeTopic,
  type PlanItem,
  type PlanToday,
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
  // The 30-day plan idea "Tạo video" starts from: "Làm tiếp" here, or "Tạo video" on an idea in Kho kiến thức.
  const [startItem, setStartItem] = useState<PlanItem | null>(null);
  // A new dialog each time it opens, so it starts from `startItem` and nothing picked before.
  const [opened, setOpened] = useState(0);
  const [today, setToday] = useState<PlanToday[]>([]);
  const router = useRouter();
  const { me } = useMe();
  const [status, setStatus] = useState<StatusFilter>("all");
  const [mine, setMine] = useState(false);
  const [view, chooseView] = useRememberedView(VIEW_KEY);

  function startFrom(item: PlanItem | null) {
    setStartItem(item);
    setOpened((count) => count + 1);
    setCreating(true);
  }

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

  useEffect(() => {
    api<PlanToday[]>("/plans/today")
      .then(setToday)
      // Only a suggestion: without it the page works as before.
      .catch(() => setToday([]));
  }, []);

  // /videos?plan_item=<id>: opened from an idea's "Tạo video" in Kho kiến thức.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("plan_item");
    if (!id) {
      return;
    }
    router.replace("/videos");
    api<PlanItem>(`/plans/items/${id}`)
      .then((item) => {
        startFrom(item);
      })
      .catch((err) => message.error(errorMessage(err)));
  }, [router, message]);

  const match = STATUS_FILTERS.find((item) => item.value === status)!.match;
  const shown = (rows ?? []).filter((row) => match(row) && (!mine || row.created_by === me.name));
  const filtered = Boolean(query.trim()) || status !== "all" || mine;

  return (
    <>
      <PageHeader
        title="Video"
        actions={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => startFrom(null)}>
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
      <PlanBanners today={today} onContinue={startFrom} />
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
      <NewVideoModal
        key={opened}
        open={creating}
        startItem={startItem}
        today={today}
        onClose={() => {
          setCreating(false);
          setStartItem(null);
        }}
      />
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
              <VideoTitleCell
                id={row.id}
                title={row.title || row.topic}
                thumbnailUrl={row.thumbnail_url}
                sub={row.title && `Chủ đề: ${row.topic}`}
              />
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

/** "Hôm nay còn X/Y video" for every topic group whose 30-day plan has a today. */
function PlanBanners({ today, onContinue }: { today: PlanToday[]; onContinue: (item: PlanItem) => void }) {
  return (
    <>
      {today
        .filter((group) => group.ideas.length > 0)
        .map((group) => {
          const left = group.ideas.filter((idea) => idea.status === "idea");
          return (
            <Alert
              key={group.topic_id}
              type={left.length ? "info" : "success"}
              showIcon
              style={{ marginBottom: 16 }}
              data-testid="plan-banner"
              title={
                left.length
                  ? `Kế hoạch ${group.name} · Ngày ${group.day}: hôm nay còn ${left.length}/${group.ideas.length} video`
                  : `Kế hoạch ${group.name} · Ngày ${group.day}: đã làm đủ ${group.ideas.length} video hôm nay`
              }
              action={
                left.length > 0 && (
                  <Button size="small" type="primary" onClick={() => onContinue(left[0])}>
                    Làm tiếp
                  </Button>
                )
              }
            />
          );
        })}
    </>
  );
}

type NewVideo = { topic: string; knowledge_topic_id: number };

/** Topics compare like the api's: case, spacing and Unicode form do not count. */
function sameTopic(a: string, b: string): boolean {
  const key = (text: string) => text.normalize("NFC").split(/\s+/).filter(Boolean).join(" ").toLowerCase();
  return key(a) === key(b);
}

function NewVideoModal({
  open,
  startItem,
  today,
  onClose,
}: {
  open: boolean;
  startItem: PlanItem | null;
  today: PlanToday[];
  onClose: () => void;
}) {
  const { message } = App.useApp();
  const router = useRouter();
  const [form] = Form.useForm<NewVideo>();
  const [busy, setBusy] = useState(false);
  const [topics, setTopics] = useState<KnowledgeTopic[] | null>(null);
  const [llm, setLlm] = useState<ActiveLlm | null>(null);
  // The plan idea the video is made from; typing a topic by hand works as before.
  const [picked, setPicked] = useState<PlanItem | null>(startItem);
  const groupId = Form.useWatch("knowledge_topic_id", form);
  const typed = Form.useWatch("topic", form) ?? "";
  const plan = today.find((group) => group.topic_id === groupId);
  const suggestions = plan?.ideas.filter((idea) => idea.status === "idea") ?? [];
  const outsidePlan = !picked && plan && typed.trim() && !plan.topics.some((topic) => sameTopic(topic, typed));

  function pick(item: PlanItem) {
    setPicked(item);
    form.setFieldsValue({ topic: item.topic });
  }

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
      const video = await api<VideoDetail>("/videos", "POST", { ...values, plan_item_id: picked?.id });
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
          initialValues={{
            knowledge_topic_id: startItem?.knowledge_topic_id ?? topics.find((topic) => topic.script_prompt)?.id,
            topic: startItem?.topic,
          }}
          onValuesChange={(changed: Partial<NewVideo>) => {
            const group = changed.knowledge_topic_id;
            if (picked && group !== undefined && group !== picked.knowledge_topic_id) {
              setPicked(null);
            }
          }}
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
          {picked ? (
            <Alert
              type="info"
              style={{ marginBottom: 16 }}
              data-testid="picked-idea"
              title={`Theo kế hoạch · Ngày ${picked.day}${picked.pain_group ? ` · ${picked.pain_group}` : ""}`}
              description={
                <>
                  {picked.pain && <div>Nỗi đau: {picked.pain}</div>}
                  {picked.hook && <div>Hook: {picked.hook}</div>}
                  <div style={{ marginTop: 4, fontSize: 12 }}>Nỗi đau và hook được gửi kèm prompt viết kịch bản.</div>
                </>
              }
              action={
                <Button size="small" type="text" onClick={() => setPicked(null)}>
                  Bỏ chọn
                </Button>
              }
            />
          ) : (
            suggestions.length > 0 && (
              <Form.Item label={`Ý tưởng hôm nay (ngày ${plan!.day}) chưa làm`}>
                <Flex vertical gap={6} data-testid="plan-suggestions">
                  {suggestions.map((idea) => (
                    <Card
                      key={idea.id}
                      size="small"
                      hoverable
                      onClick={() => pick(idea)}
                      styles={{ body: { padding: "6px 10px" } }}
                    >
                      <Typography.Text>{idea.topic}</Typography.Text>
                      {idea.pain_group && <Tag style={{ marginInlineStart: 8 }}>{idea.pain_group}</Tag>}
                    </Card>
                  ))}
                </Flex>
              </Form.Item>
            )
          )}
          {outsidePlan && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
              data-testid="outside-plan"
              title="Chủ đề này không có trong kế hoạch 30 ngày của nhóm. Vẫn tạo được bình thường."
            />
          )}
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
