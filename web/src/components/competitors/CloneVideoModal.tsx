"use client";

import {
  Alert,
  App,
  Button,
  Flex,
  Input,
  Modal,
  Segmented,
  Select,
  Skeleton,
  Typography,
  type SelectProps,
} from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";
import EmptyState from "@/components/EmptyState";
import { api, errorMessage, type Knowledge, type KnowledgeTopic } from "@/lib/api";
import { loadLastChoices, saveLastChoice } from "@/lib/lastChoices";
import type { VideoRow } from "./types";

/** GET /competitors/{id}/videos/{fb_video_id}/clone-preview (api routes_competitors.clone_preview). */
type Preview = {
  topic: string;
  script: string;
  scenes: number;
  thin: boolean;
  comment_count: number;
  can_scan_comments: boolean;
  comments_scan: { id: number; status: "queued" | "running" } | null;
};

const EMPTY: Preview = {
  topic: "",
  script: "",
  scenes: 0,
  thin: false,
  comment_count: 0,
  can_scan_comments: false,
  comments_scan: null,
};

type Made = { video_id: number; url: string; scenes: number; thin: boolean; has_comments: boolean };

type Mode = "group" | "slides" | "single";

const MODES: { value: Mode; label: string }[] = [
  { value: "group", label: "Theo nhóm" },
  { value: "slides", label: "Slide ảnh" },
  { value: "single", label: "Video xuyên suốt" },
];

function groupOptions(topics: KnowledgeTopic[]): NonNullable<SelectProps["options"]> {
  const option = (topic: KnowledgeTopic) => ({ value: topic.id, label: topic.name });
  const mine = topics.filter((topic) => topic.mine).map(option);
  const others = topics.filter((topic) => !topic.mine).map(option);
  if (mine.length === 0 || others.length === 0) return [...mine, ...others];
  return [
    { label: "Nhóm của tôi", title: "Nhóm của tôi", options: mine },
    { label: "Nhóm khác", title: "Nhóm khác", options: others },
  ];
}

/**
 * "Clone video": a "Tự viết" video built in code from the competitor's caption (no AI, no cost); the member checks
 * the title and script, picks the group, and gets a link to the new video, where photos and clips are added by hand.
 */
export default function CloneVideoModal({
  competitorId,
  video,
  onClose,
}: {
  competitorId: number;
  video: VideoRow;
  onClose: () => void;
}) {
  const { message, notification } = App.useApp();
  const base = `/competitors/${competitorId}/videos/${video.fb_video_id}`;
  const [preview, setPreview] = useState<Preview | null>(null);
  const [failed, setFailed] = useState("");
  const [topics, setTopics] = useState<KnowledgeTopic[] | null>(null);
  const [groupId, setGroupId] = useState<number | null>(null);
  const [mode, setMode] = useState<Mode>("group");
  const [topic, setTopic] = useState("");
  const [script, setScript] = useState("");
  const [saving, setSaving] = useState(false);
  const [queueing, setQueueing] = useState(false);

  useEffect(() => {
    let live = true;
    api<Preview>(`${base}/clone-preview`).then(
      (data) => {
        if (!live) return;
        setPreview(data);
        setTopic(data.topic);
        setScript(data.script);
      },
      (err) => live && setFailed(errorMessage(err)),
    );
    Promise.all([api<Knowledge>("/knowledge"), loadLastChoices()]).then(
      ([data, last]) => {
        if (!live) return;
        setTopics(data.topics);
        if (last.knowledge_topic_id && data.topics.some((item) => item.id === last.knowledge_topic_id)) {
          setGroupId(last.knowledge_topic_id);
        }
      },
      (err) => live && setFailed(errorMessage(err)),
    );
    return () => {
      live = false;
    };
  }, [base]);

  async function create() {
    if (groupId === null) {
      message.error("Hãy chọn nhóm chủ đề");
      return;
    }
    setSaving(true);
    try {
      const made = await api<Made>(`${base}/clone`, "POST", {
        knowledge_topic_id: groupId,
        video_mode: mode === "group" ? null : mode,
        topic,
        script,
      });
      void saveLastChoice({ knowledge_topic_id: groupId });
      const key = `clone-${made.video_id}`;
      notification.success({
        key,
        title: "Đã tạo video",
        description: `${made.scenes} cảnh. Gắn ảnh hoặc clip cho từng cảnh ở trang video rồi render.`,
        actions: (
          <Flex gap={12} align="center">
            <Button size="small" onClick={() => notification.destroy(key)}>
              Ở lại trang
            </Button>
            <Link prefetch={false} href={made.url} onClick={() => notification.destroy(key)} data-testid="clone-open">
              Mở video
            </Link>
          </Flex>
        ),
        duration: 10,
      });
      onClose();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function scanComments() {
    setQueueing(true);
    try {
      const scan = await api<{ id: number; status: "queued" | "running" }>(`${base}/scan-comments`, "POST");
      setPreview((old) => (old ? { ...old, comments_scan: { id: scan.id, status: scan.status } } : old));
      message.success("Đã xếp lượt quét bình luận; trang này sẽ chạy nó khi tiện ích sẵn sàng");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setQueueing(false);
    }
  }

  const loading = !failed && (!preview || !topics);
  const info: Preview = preview ?? { ...EMPTY };
  return (
    <Modal
      open
      title="Clone video"
      onCancel={onClose}
      width={640}
      okText="Tạo video"
      cancelText="Hủy"
      onOk={create}
      okButtonProps={{ loading: saving, disabled: loading || Boolean(failed) || !topic.trim() || !script.trim() }}
      destroyOnHidden
    >
      {failed ? (
        <EmptyState description={failed} />
      ) : loading ? (
        <Skeleton active paragraph={{ rows: 6 }} title={false} />
      ) : (
        <Flex vertical gap={12} data-testid="clone-modal">
          <Typography.Text type="secondary">
            Kịch bản dựng từ caption của video đối thủ, không dùng AI và không tốn phí. Ảnh, clip và giọng đọc làm ở
            trang video.
          </Typography.Text>
          <Flex vertical gap={4}>
            <Typography.Text strong>Nhóm chủ đề</Typography.Text>
            <Select
              aria-label="Nhóm chủ đề"
              placeholder="Chọn nhóm chủ đề"
              value={groupId ?? undefined}
              onChange={(value: number) => setGroupId(value)}
              options={groupOptions(topics ?? [])}
              showSearch
              optionFilterProp="label"
              status={groupId === null ? "warning" : undefined}
            />
          </Flex>
          <Flex vertical gap={4}>
            <Typography.Text strong>Kiểu video</Typography.Text>
            <Segmented<Mode> value={mode} onChange={setMode} options={MODES} style={{ alignSelf: "start" }} />
          </Flex>
          <Flex vertical gap={4}>
            <Typography.Text strong>Tiêu đề</Typography.Text>
            <Input
              aria-label="Tiêu đề"
              value={topic}
              maxLength={300}
              onChange={(event) => setTopic(event.target.value)}
            />
          </Flex>
          <Flex vertical gap={4}>
            <Typography.Text strong>Kịch bản</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Mỗi đoạn (cách nhau một dòng trống) là một cảnh; dòng “Đọc:” là lời đọc của cảnh.
            </Typography.Text>
            <Input.TextArea
              aria-label="Kịch bản"
              value={script}
              maxLength={5000}
              autoSize={{ minRows: 6, maxRows: 14 }}
              onChange={(event) => setScript(event.target.value)}
            />
          </Flex>
          {info.thin && (
            <Alert
              type="info"
              showIcon
              title="Caption ngắn: video chỉ có khung hook. Bạn thêm ý ở trang video, hoặc nhờ Claude viết tiếp qua MCP."
            />
          )}
          <Flex gap={8} align="center" wrap>
            <Typography.Text type="secondary" data-testid="clone-comments">
              Bình luận mẫu: {info.comment_count > 0 ? `có ${info.comment_count}` : "chưa có"}
            </Typography.Text>
            {info.comments_scan ? (
              <Typography.Text type="secondary">
                ({info.comments_scan.status === "running" ? "đang quét" : "đang chờ quét"})
              </Typography.Text>
            ) : (
              info.comment_count === 0 &&
              info.can_scan_comments && (
                <Button size="small" loading={queueing} onClick={scanComments}>
                  Quét bình luận video này
                </Button>
              )
            )}
          </Flex>
        </Flex>
      )}
    </Modal>
  );
}
