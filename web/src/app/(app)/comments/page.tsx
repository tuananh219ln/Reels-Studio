"use client";

import { ReloadOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Empty, Flex, Input, Popconfirm, Segmented, Typography } from "antd";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorMessage, formatDateTime, type PageCommentRow, type PageComments } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { useFreshenOnOpen } from "@/lib/freshen";
import { usePolling } from "@/lib/polling";
import StatusText, { type StatusTone } from "@/components/StatusText";
import FilterSelect from "@/components/FilterSelect";

const REFRESH_MS = 10_000;

const STATE: Record<PageCommentRow["state"], { label: string; tone: StatusTone }> = {
  open: { label: "Chưa trả lời", tone: "waiting" },
  sending: { label: "Đang gửi…", tone: "active" },
  answered: { label: "Đã trả lời", tone: "success" },
  hidden: { label: "Đã ẩn", tone: "idle" },
  dismissed: { label: "Bỏ qua", tone: "idle" },
};

/** One comment: who, what, under which reel, and the reply box. */
function CommentCard({ row, onChanged }: { row: PageCommentRow; onChanged: (row: PageCommentRow) => void }) {
  const { message } = App.useApp();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const canAnswer = row.state === "open" || row.state === "dismissed";

  async function run(action: string, body?: object) {
    setBusy(action);
    try {
      onChanged(await api<PageCommentRow>(`/comments/${row.id}/${action}`, "POST", body));
      if (action === "reply") setText("");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card size="small" data-testid="page-comment">
      <Flex vertical gap={6}>
        <Flex justify="space-between" gap={8} wrap>
          <Typography.Text strong>{row.author || "Người xem"}</Typography.Text>
          <Flex gap={6} align="center">
            <StatusText tone={STATE[row.state].tone}>{STATE[row.state].label}</StatusText>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {formatDateTime(row.created_at)}
            </Typography.Text>
          </Flex>
        </Flex>
        <Typography.Paragraph style={{ margin: 0, whiteSpace: "pre-wrap" }}>{row.message}</Typography.Paragraph>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {row.post.fanpage},{" "}
          <Link
            prefetch={false}
            href={row.post.article_id ? `/articles/${row.post.article_id}` : `/videos/${row.post.video_id}`}
          >
            {row.post.title}
          </Link>
          {row.post.reel_url && (
            <>
              {", "}
              <a href={row.post.reel_url} target="_blank" rel="noreferrer">
                {row.post.article_id ? "Xem bài" : "Xem Reel"}
              </a>
            </>
          )}
        </Typography.Text>
        {row.reply_text && (
          <Typography.Text type="secondary">
            Trả lời{row.handled_by ? ` (${row.handled_by})` : ""}: {row.reply_text}
          </Typography.Text>
        )}
        {row.error && <Alert type="error" showIcon title={row.error} />}
        {canAnswer && (
          <Flex vertical gap={6}>
            <Input.TextArea
              aria-label="Trả lời"
              value={text}
              autoSize={{ minRows: 1, maxRows: 5 }}
              maxLength={2000}
              placeholder="Trả lời với tư cách Page"
              onChange={(event) => setText(event.target.value)}
            />
            <Flex gap={8} wrap>
              <Button
                type="primary"
                size="small"
                disabled={!text.trim()}
                loading={busy === "reply"}
                onClick={() => run("reply", { text })}
              >
                Gửi trả lời
              </Button>
              <Popconfirm
                title="Ẩn bình luận này trên Facebook?"
                description="Người viết và bạn bè họ vẫn thấy, người khác thì không."
                okText="Ẩn"
                cancelText="Không"
                onConfirm={() => run("hide")}
              >
                <Button size="small" loading={busy === "hide"}>
                  Ẩn
                </Button>
              </Popconfirm>
              <Button
                size="small"
                type="text"
                loading={busy === "dismiss"}
                onClick={() => run("dismiss", { dismissed: row.state !== "dismissed" })}
              >
                {row.state === "dismissed" ? "Đưa lại vào chưa trả lời" : "Bỏ qua"}
              </Button>
            </Flex>
          </Flex>
        )}
      </Flex>
    </Card>
  );
}

export default function CommentsPage() {
  const { message } = App.useApp();
  const [view, setView] = useState<"open" | "all">("open");
  const [data, setData] = useState<PageComments | null>(null);
  const [fanpage, setFanpage] = useState<number | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api<PageComments>(`/comments?state=${view}`));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [view, message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads when the view changes; state is set only after the request answers
    void load();
  }, [load]);
  usePolling(load, REFRESH_MS);
  // Reels not read lately are read again on opening, without pressing "Tải bình luận mới".
  useFreshenOnOpen("/comments/freshen", load);

  async function refresh() {
    setRefreshing(true);
    try {
      await api("/comments/refresh", "POST");
      message.success("Đã nhờ worker tải bình luận mới, danh sách tự cập nhật sau ít giây");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setRefreshing(false);
    }
  }

  const pages = useMemo(() => {
    const seen = new Map<number, string>();
    for (const row of data?.comments ?? []) {
      if (row.post.fanpage_id !== null) seen.set(row.post.fanpage_id, row.post.fanpage ?? "");
    }
    return [...seen].map(([value, label]) => ({ value, label }));
  }, [data]);
  const rows = (data?.comments ?? []).filter((row) => fanpage === null || row.post.fanpage_id === fanpage);

  function changed(row: PageCommentRow) {
    setData(
      (current) => current && { ...current, comments: current.comments.map((one) => (one.id === row.id ? row : one)) },
    );
  }

  return (
    <>
      <PageHeader
        title="Bình luận"
        actions={
          <Button icon={<ReloadOutlined />} loading={refreshing} onClick={refresh}>
            Tải bình luận mới
          </Button>
        }
        description={
          <>
            Bình luận của người xem dưới các reel app đã đăng trong 14 ngày gần nhất, tải về mỗi 30 phút. Câu trả lời
            gửi với tư cách Page.
            {data?.read_at && ` Lần tải gần nhất: ${formatDateTime(data.read_at)}.`}
          </>
        }
      />
      <Flex vertical gap={12}>
        {data?.read_errors.map((item) => (
          <Alert key={item.fanpage + item.error} type="warning" showIcon title={`${item.fanpage}: ${item.error}`} />
        ))}
        <Flex gap={8} wrap>
          <Segmented
            value={view}
            onChange={(value) => setView(value as "open" | "all")}
            options={[
              { value: "open", label: "Chưa trả lời" },
              { value: "all", label: "Tất cả" },
            ]}
          />
          {pages.length > 1 && (
            <FilterSelect
              aria-label="Fanpage"
              placeholder="Mọi Fanpage"
              value={fanpage}
              onChange={(value) => setFanpage(value ?? null)}
              options={pages}
              style={{ minWidth: 200 }}
            />
          )}
        </Flex>
        {data && rows.length === 0 ? (
          <Card>
            <Empty description={view === "open" ? "Không còn bình luận nào chờ trả lời" : "Chưa có bình luận nào"} />
          </Card>
        ) : (
          rows.map((row) => <CommentCard key={row.id} row={row} onChanged={changed} />)
        )}
      </Flex>
    </>
  );
}
