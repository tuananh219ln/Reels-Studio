"use client";
import AutoApproveSwitch from "@/components/actions/AutoApproveSwitch";
import VideoActions from "@/components/actions/VideoActions";
import { usePolling } from "@/lib/polling";

import EmptyState from "@/components/EmptyState";
import { PostedPlatforms, VideoKindTags } from "@/components/VideoKind";
import VideoStatusTags from "@/components/VideoStatusTags";
import { api, errorMessage, formatDateTime, type VideoRow } from "@/lib/api";
import { useUrlChoiceIf, useUrlPageIf } from "@/lib/urlState";
import { VIDEO_STATUS_FILTERS } from "@/lib/videoStatus";
import { AppstoreOutlined, PlusOutlined, SearchOutlined, TableOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Input, Segmented, Table, Tabs, Typography, theme } from "antd";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

/** Accents and case ignored, so "rau mam" finds "Rau mầm". */
function plain(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/gi, "d").toLowerCase();
}

type View = "table" | "list";
const VIEW_KEY = "topic-videos-view";

/** "Bảng | Danh sách", remembered in this browser, as useRememberedView (lib/view.ts) does; the table until chosen. */
function useView(): [View, (view: View) => void] {
  const [view, setView] = useState<View>(() => {
    try {
      return window.localStorage.getItem(VIEW_KEY) === "list" ? "list" : "table";
    } catch {
      return "table";
    }
  });
  return [
    view,
    (next) => {
      setView(next);
      try {
        window.localStorage.setItem(VIEW_KEY, next);
      } catch {
        // Not remembered, still shown.
      }
    },
  ];
}

const count = (value: number | null | undefined) => (value == null ? "—" : value.toLocaleString("vi-VN"));
const percent = (value: number | null | undefined) =>
  value == null
    ? "—"
    : `${(value * 100).toLocaleString("vi-VN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;

/** A posted video's numbers; a video not out yet shows dashes, never a zero it does not have. */
function numbers(row: VideoRow) {
  const post = row.post?.state === "posted" ? row.post : null;
  return {
    views: post?.views ?? null,
    views48: post?.views_48h ?? null,
    shares: post?.shares ?? null,
    rate: post?.share_rate ?? null,
  };
}

/** "Video" in Kho kiến thức: the videos of one topic group, newest first, each opening its video page. */
export default function TopicVideos({
  topicId,
  canCreate,
  visible = true,
}: {
  topicId: number;
  canCreate: boolean;
  /** Whether its group is the one shown: only then are the search, filter and page in the address. */
  visible?: boolean;
}) {
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const [rows, setRows] = useState<VideoRow[] | null>(null);
  const [search, setSearch] = useUrlChoiceIf<string>(visible, "q", "");
  const [status, setStatus] = useUrlChoiceIf<string | null>(visible, "status", null);
  const tablePage = useUrlPageIf(visible);
  const [view, setView] = useView();

  const load = useCallback(
    async (quiet = false) => {
      try {
        setRows(await api<VideoRow[]>(`/videos?knowledge_topic_id=${topicId}`));
      } catch (err) {
        if (!quiet) message.error(errorMessage(err));
      }
    },
    [topicId, message],
  );
  useEffect(() => {
    let live = true;
    api<VideoRow[]>(`/videos?knowledge_topic_id=${topicId}`).then(
      (found) => {
        if (live) setRows(found);
      },
      (err) => {
        if (live) {
          setRows([]);
          message.error(errorMessage(err));
        }
      },
    );
    return () => {
      live = false;
    };
  }, [topicId, message]);
  usePolling(
    async () => {
      if (visible) await load(true);
    },
    rows?.some((row) => !["draft", "done", "failed"].includes(row.status)) ? 5000 : 60000,
  );

  // Every choice, with how many of the group's videos are in it, so a group of finished videos still shows the rest.
  const choice = VIDEO_STATUS_FILTERS.find((item) => item.value === status);
  const wanted = plain(search.trim());
  const shown = (rows ?? []).filter(
    (row) =>
      (!choice || choice.match(row)) &&
      (!wanted || plain(row.title).includes(wanted) || plain(row.topic).includes(wanted)),
  );

  return (
    <Flex vertical gap={12} data-testid="topic-videos">
      <Tabs
        size="small"
        activeKey={status ?? "all"}
        onChange={(key) => setStatus(key === "all" ? null : key)}
        tabBarStyle={{ marginBottom: 0 }}
        items={[
          { key: "all", label: `Tất cả (${(rows ?? []).length})` },
          ...VIDEO_STATUS_FILTERS.map(({ value, label, match }) => ({
            key: value,
            label: `${label} (${(rows ?? []).filter(match).length})`,
          })),
        ]}
      />
      <Flex wrap gap={8} justify="space-between">
        <Flex wrap gap={8}>
          <Input
            aria-label="Tìm video của nhóm"
            placeholder="Tìm theo tiêu đề hoặc chủ đề…"
            prefix={<SearchOutlined />}
            allowClear
            style={{ width: 260 }}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <Segmented<View>
            aria-label="Chế độ hiển thị"
            value={view}
            onChange={setView}
            options={[
              { value: "table", label: "Bảng", icon: <TableOutlined /> },
              { value: "list", label: "Danh sách", icon: <AppstoreOutlined /> },
            ]}
          />
        </Flex>
        <Flex wrap gap={16} align="center">
          <AutoApproveSwitch />
          {canCreate && (
            <Link prefetch={false} href={`/videos?group=${topicId}`}>
              <Button type="primary" icon={<PlusOutlined />}>
                Tạo video
              </Button>
            </Link>
          )}
        </Flex>
      </Flex>
      {view === "list" ? (
        <VideoCards rows={rows} shown={shown} onChanged={() => load(true)} />
      ) : (
        <Table<VideoRow>
          size="small"
          rowKey="id"
          loading={rows === null}
          dataSource={shown}
          pagination={shown.length > 20 ? { pageSize: 20, showSizeChanger: false, ...tablePage } : false}
          // As wide as its columns need, scrolling inside the card: no column is cut at its edge.
          scroll={{ x: "max-content" }}
          locale={{
            emptyText: (
              <EmptyState description={rows?.length ? "Không có video nào khớp" : "Nhóm này chưa có video nào"} />
            ),
          }}
          columns={[
            {
              key: "thumbnail",
              width: 56,
              render: (_, row) =>
                row.thumbnail_url ? (
                  // eslint-disable-next-line @next/next/no-img-element -- the api serves the thumbnail; next/image adds nothing here
                  <img
                    src={row.thumbnail_url}
                    alt=""
                    loading="lazy"
                    width={36}
                    height={64}
                    style={{ objectFit: "cover", borderRadius: token.borderRadiusSM, display: "block" }}
                  />
                ) : (
                  <div
                    style={{
                      width: 36,
                      height: 64,
                      borderRadius: token.borderRadiusSM,
                      background: token.colorFillTertiary,
                    }}
                  />
                ),
            },
            {
              key: "title",
              title: "Video",
              minWidth: 260,
              render: (_, row) => (
                <Flex vertical style={{ minWidth: 0 }}>
                  <Link prefetch={false} href={`/videos/${row.id}`}>
                    <Typography.Text strong ellipsis style={{ color: "inherit", maxWidth: 300 }}>
                      {row.title || row.topic}
                    </Typography.Text>
                  </Link>
                  <Typography.Text type="secondary" ellipsis style={{ fontSize: 13, maxWidth: 300 }}>
                    {row.topic}
                    {row.plan_day ? `, kế hoạch ngày ${row.plan_day}` : ""}
                  </Typography.Text>
                </Flex>
              ),
            },
            {
              key: "kind",
              title: "Loại",
              width: 120,
              render: (_, row) => <VideoKindTags video={row} />,
            },
            {
              key: "status",
              title: "Trạng thái",
              width: 150,
              // Where it is out sits beside "Đã đăng", not in a column of its own.
              render: (_, row) => (
                <Flex gap={8} align="center" wrap>
                  <VideoStatusTags video={row} />
                  <PostedPlatforms postedOn={row.posted_on} />
                </Flex>
              ),
            },
            {
              key: "views",
              title: "View",
              width: 90,
              align: "right",
              render: (_, row) => count(numbers(row).views),
            },
            {
              key: "views48",
              title: "View 48h",
              width: 90,
              align: "right",
              render: (_, row) => count(numbers(row).views48),
            },
            {
              key: "shares",
              title: "Share",
              width: 70,
              align: "right",
              render: (_, row) => count(numbers(row).shares),
            },
            {
              key: "rate",
              title: "Share/view",
              width: 100,
              align: "right",
              render: (_, row) => percent(numbers(row).rate),
            },
            {
              key: "made",
              title: "Tạo",
              width: 150,
              render: (_, row) => (
                <Flex vertical>
                  <Typography.Text ellipsis>{row.created_by}</Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {formatDateTime(row.created_at)}
                  </Typography.Text>
                </Flex>
              ),
            },
            {
              key: "actions",
              // Room for "Duyệt" beside the ⋮ of a ready video, no more: the bin that filled the rest is gone.
              width: 88,
              // Pinned to the right: the table scrolls sideways, and the actions must show without scrolling.
              fixed: "right",
              render: (_, row) => (
                <Flex>
                  <VideoActions video={row} onChanged={() => load(true)} />
                </Flex>
              ),
            },
          ]}
        />
      )}
    </Flex>
  );
}

/** "Danh sách": a card per video, with a larger picture, its status and its main numbers. */
function VideoCards({
  rows,
  shown,
  onChanged,
}: {
  rows: VideoRow[] | null;
  shown: VideoRow[];
  onChanged: () => Promise<void>;
}) {
  const { token } = theme.useToken();
  if (rows !== null && shown.length === 0) {
    return <EmptyState description={rows.length ? "Không có video nào khớp" : "Nhóm này chưa có video nào"} />;
  }
  return (
    <Flex vertical gap={8} data-testid="topic-video-cards">
      {(rows === null ? [] : shown).map((row) => {
        const figures = numbers(row);
        return (
          <Card key={row.id} size="small" data-testid="topic-video-card" styles={{ body: { padding: 10 } }}>
            <Flex gap={12} align="flex-start">
              {row.thumbnail_url ? (
                // eslint-disable-next-line @next/next/no-img-element -- the api serves the thumbnail; next/image adds nothing here
                <img
                  src={row.thumbnail_url}
                  alt=""
                  loading="lazy"
                  width={72}
                  height={128}
                  style={{ objectFit: "cover", borderRadius: token.borderRadius, display: "block", flex: "none" }}
                />
              ) : (
                <div
                  style={{
                    width: 72,
                    height: 128,
                    flex: "none",
                    borderRadius: token.borderRadius,
                    background: token.colorFillTertiary,
                  }}
                />
              )}
              <Flex vertical gap={6} style={{ minWidth: 0, flex: 1 }}>
                <Flex justify="space-between" align="flex-start" gap={8}>
                  <Link prefetch={false} href={`/videos/${row.id}`}>
                    <Typography.Text strong style={{ color: "inherit" }}>
                      {row.title || row.topic}
                    </Typography.Text>
                  </Link>
                  <Flex>
                    <VideoActions video={row} onChanged={onChanged} />
                  </Flex>
                </Flex>
                <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                  {row.topic}
                  {row.plan_day ? `, kế hoạch ngày ${row.plan_day}` : ""}, {row.created_by},{" "}
                  {formatDateTime(row.created_at)}
                </Typography.Text>
                <VideoKindTags video={row} />
                <Flex wrap gap={8} align="center">
                  <VideoStatusTags video={row} />
                  <PostedPlatforms postedOn={row.posted_on} />
                </Flex>
                <Typography.Text type="secondary" style={{ fontSize: 13 }} data-testid="topic-video-numbers">
                  {figures.views === null && figures.views48 === null
                    ? "Chưa có số liệu đăng"
                    : `${count(figures.views)} view; 48h: ${count(figures.views48)} view, ${count(figures.shares)} share, share/view ${percent(figures.rate)}`}
                </Typography.Text>
              </Flex>
            </Flex>
          </Card>
        );
      })}
    </Flex>
  );
}
