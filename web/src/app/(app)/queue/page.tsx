"use client";

import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Empty, Flex, Popconfirm, Segmented, Select, Spin, Typography } from "antd";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type QueueOverview, type QueuePage } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import StatusText from "@/components/StatusText";
import VideoThumbnail from "@/components/VideoThumbnail";
import { usePolling } from "@/lib/polling";

const REFRESH_MS = 30_000;
const TIME = /^([01]?\d|2[0-3]):[0-5]\d$/;

/** One Page: its topic group and posting times (its owner changes them), the free times ahead, and its queue. */
function PageQueue({
  page,
  overview,
  onChanged,
}: {
  page: QueuePage;
  overview: QueueOverview;
  onChanged: (overview: QueueOverview) => void;
}) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);

  async function run(path: string, method: "PATCH" | "POST" | "DELETE", body?: object) {
    setBusy(true);
    try {
      onChanged(await api<QueueOverview>(path, method, body));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function move(index: number, by: number) {
    const ids = page.items.map((item) => item.id);
    [ids[index], ids[index + by]] = [ids[index + by], ids[index]];
    void run(`/queue/pages/${page.id}/order`, "POST", { ids });
  }

  function setTimes(times: string[]) {
    const bad = times.find((value) => !TIME.test(value.trim()));
    if (bad) {
      message.error(`Giờ đăng “${bad}” phải có dạng HH:MM`);
      return;
    }
    void run(`/queue/pages/${page.id}`, "PATCH", { post_times: times.length ? times : null });
  }

  return (
    <Card
      size="small"
      data-testid="queue-page"
      title={
        <Flex gap={8} align="center" wrap>
          <Typography.Text strong>{page.name}</Typography.Text>
          {page.owner && (
            <Typography.Text type="secondary" style={{ fontWeight: 400 }}>
              {page.owner.name}
            </Typography.Text>
          )}
        </Flex>
      }
      extra={
        page.healthy ? (
          <StatusText tone="success">Token ổn</StatusText>
        ) : (
          <StatusText tone="danger" title={page.check_error ?? undefined}>
            Token lỗi, tạm dừng
          </StatusText>
        )
      }
    >
      <Spin spinning={busy}>
        <Flex vertical gap={12}>
          {page.mine ? (
            <Flex gap={12} wrap align="center">
              <Select
                aria-label={`Nhóm chủ đề của ${page.name}`}
                placeholder="Chọn nhóm chủ đề"
                value={page.topic?.id ?? null}
                style={{ minWidth: 220 }}
                allowClear
                onChange={(value) => run(`/queue/pages/${page.id}`, "PATCH", { knowledge_topic_id: value ?? null })}
                options={overview.topics.map((topic) => ({ value: topic.id, label: topic.name }))}
              />
              <Select
                mode="tags"
                aria-label={`Giờ đăng của ${page.name}`}
                placeholder="Giờ đăng, ví dụ 20:00"
                value={page.post_times}
                style={{ minWidth: 260 }}
                tokenSeparators={[",", " "]}
                onChange={setTimes}
                options={page.post_times.map((value) => ({ value, label: value }))}
              />
              {page.own_times && page.topic && (
                <Button size="small" onClick={() => setTimes([])}>
                  Dùng giờ của nhóm
                </Button>
              )}
            </Flex>
          ) : (
            <Typography.Text type="secondary">
              {page.topic ? `Nhóm “${page.topic.name}”` : "Chưa gắn nhóm chủ đề"}
              {page.post_times.length > 0 && `, đăng lúc ${page.post_times.join(", ")}`}
            </Typography.Text>
          )}
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {page.post_times.length === 0
              ? "Chưa có giờ đăng: hãy gắn nhóm chủ đề hoặc nhập giờ riêng."
              : page.own_times
                ? "Giờ riêng của Page (giờ Việt Nam)."
                : "Theo giờ đăng của nhóm chủ đề (giờ Việt Nam)."}
            {page.free_slots.length > 0 &&
              ` Khung trống trong ${overview.fill_ahead_hours} giờ tới: ${page.free_slots.map(formatDateTime).join(", ")}.`}
          </Typography.Text>
          {page.items.length === 0 ? (
            <Typography.Text type="secondary">Hàng chờ trống.</Typography.Text>
          ) : (
            <Flex vertical gap={8}>
              {page.items.map((item, index) => (
                <Flex key={item.id} gap={10} align="center" data-testid="queue-item">
                  <Typography.Text type="secondary" style={{ width: 20 }}>
                    {index + 1}
                  </Typography.Text>
                  <VideoThumbnail name={item.video.title} url={item.video.thumbnail_url} width={36} />
                  <Flex vertical style={{ minWidth: 0, flex: 1 }}>
                    <Link prefetch={false} href={`/videos/${item.video.id}`}>
                      {item.video.title}
                    </Link>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {item.added_by}, {formatDateTime(item.added_at)}
                    </Typography.Text>
                    {item.error && (
                      <Typography.Text type="warning" style={{ fontSize: 12 }}>
                        Chưa lên lịch được: {item.error}
                      </Typography.Text>
                    )}
                  </Flex>
                  {page.mine && (
                    <>
                      <Button
                        size="small"
                        aria-label="Lên"
                        icon={<ArrowUpOutlined />}
                        disabled={index === 0}
                        onClick={() => move(index, -1)}
                      />
                      <Button
                        size="small"
                        aria-label="Xuống"
                        icon={<ArrowDownOutlined />}
                        disabled={index === page.items.length - 1}
                        onClick={() => move(index, 1)}
                      />
                    </>
                  )}
                  <Popconfirm
                    title="Bỏ video khỏi hàng chờ?"
                    okText="Bỏ"
                    cancelText="Không"
                    onConfirm={() => run(`/queue/items/${item.id}`, "DELETE")}
                  >
                    <Button size="small" aria-label="Bỏ khỏi hàng chờ" icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Flex>
              ))}
            </Flex>
          )}
        </Flex>
      </Spin>
    </Card>
  );
}

export default function QueuePageView() {
  const [overview, setOverview] = useState<QueueOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scope, setScope] = useState<"mine" | "all">("mine");

  const load = useCallback(
    () =>
      api<QueueOverview>("/queue").then(
        (answer) => {
          setOverview(answer);
          setError(null);
        },
        (err) => setError(errorMessage(err)),
      ),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  usePolling(load, REFRESH_MS);

  const pages = overview?.pages.filter((page) => scope === "all" || page.mine) ?? [];
  return (
    <>
      <PageHeader
        title="Hàng chờ"
        description={
          <>
            Mỗi Page đăng một nhóm chủ đề vào giờ đăng của nó. Video thêm vào hàng chờ tự lên lịch trên Facebook vào
            khung trống gần nhất, trước tối đa {overview?.fill_ahead_hours ?? 48} giờ. Xem lịch đã hẹn ở{" "}
            <Link prefetch={false} href="/posts?view=calendar">
              Bài đăng
            </Link>
            .
          </>
        }
      >
        <Segmented
          value={scope}
          onChange={(value) => setScope(value as "mine" | "all")}
          options={[
            { value: "mine", label: "Page của tôi" },
            { value: "all", label: "Mọi Page" },
          ]}
        />
      </PageHeader>
      {error && <Alert type="error" showIcon title={error} style={{ marginBottom: 12 }} />}
      {overview === null ? (
        <Spin />
      ) : pages.length === 0 ? (
        <Empty
          description={
            <>
              Chưa có Page nào.{" "}
              <Link prefetch={false} href="/fanpages">
                Kết nối Fanpage
              </Link>{" "}
              hoặc nhận Page ở đó.
            </>
          }
        />
      ) : (
        <div
          style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 460px), 1fr))" }}
        >
          {pages.map((page) => (
            <PageQueue key={page.id} page={page} overview={overview} onChanged={setOverview} />
          ))}
        </div>
      )}
    </>
  );
}
