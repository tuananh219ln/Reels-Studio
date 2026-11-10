"use client";

import EmptyState from "@/components/EmptyState";
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DownloadOutlined,
  EllipsisOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { App, Button, Card, Checkbox, Dropdown, Flex, Popover, Table, Tooltip, Typography, theme } from "antd";
import type { TableColumnsType, TablePaginationConfig } from "antd";
import type { SorterResult } from "antd/es/table/interface";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import StatusText from "@/components/StatusText";
import VideoThumbnail from "@/components/VideoThumbnail";
import { formatNumber, formatSeconds } from "@/components/page/Figures";
import { api, errorMessage, formatDateTime, type PageContent, type PageContentPost } from "@/lib/api";
import { useUrlChoice, useUrlPage } from "@/lib/urlState";
import { usePolling } from "@/lib/polling";

const REFRESH_MS = 60_000;
// Remembered in this browser, like the list or grid choice of other pages.
const COLUMNS_KEY = "page-content-columns";

const times = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 });

type Key =
  | "live_at"
  | "status"
  | "views"
  | "reach"
  | "reactions"
  | "comments"
  | "shares"
  | "avg_watch_seconds"
  | "followers"
  | "views_48h"
  | "times_median";

type Column = {
  key: Key;
  title: string;
  tip?: string;
  /** The value sorted on and written to the CSV file; null sorts last either way. */
  value: (post: PageContentPost) => number | string | null;
  render: (post: PageContentPost) => React.ReactNode;
  numeric?: boolean;
};

function latest(metric: keyof NonNullable<PageContentPost["numbers"]>) {
  return (post: PageContentPost) => {
    const value = post.numbers?.[metric];
    return typeof value === "number" ? value : null;
  };
}

function Times({ value }: { value: number | null }) {
  const { token } = theme.useToken();
  if (value === null) return <Typography.Text type="secondary">—</Typography.Text>;
  const up = value >= 1;
  // The arrow carries the direction, so it is never colour alone.
  return (
    <span style={{ color: up ? token.colorSuccessText : token.colorTextSecondary, whiteSpace: "nowrap" }}>
      {up ? <ArrowUpOutlined /> : <ArrowDownOutlined />} {times.format(value)}×
    </span>
  );
}

const COLUMNS: Column[] = [
  {
    key: "live_at",
    title: "Lên lúc",
    value: (post) => post.live_at,
    render: (post) => <span style={{ whiteSpace: "nowrap" }}>{formatDateTime(post.live_at)}</span>,
  },
  {
    key: "status",
    title: "Trạng thái",
    value: (post) => (post.status === "deleted" ? "Đã gỡ" : "Đã đăng"),
    render: (post) =>
      post.status === "deleted" ? (
        <StatusText tone="idle" title={post.closed_at ? `Gỡ lúc ${formatDateTime(post.closed_at)}` : undefined}>
          Đã gỡ
        </StatusText>
      ) : (
        <StatusText tone="success">Đã đăng</StatusText>
      ),
  },
  ...(
    [
      ["views", "Lượt xem", undefined],
      ["reach", "Tiếp cận", "Số người đã thấy reel, Facebook ước tính"],
      ["reactions", "Cảm xúc", undefined],
      ["comments", "Bình luận", undefined],
      ["shares", "Chia sẻ", undefined],
      ["followers", "Theo dõi", "Người theo dõi Page nhờ reel này"],
    ] as const
  ).map(([key, title, tip]): Column => ({
    key,
    title,
    tip,
    numeric: true,
    value: latest(key),
    render: (post) => formatNumber(latest(key)(post)),
  })),
  {
    key: "avg_watch_seconds",
    title: "Xem TB",
    tip: "Thời gian xem trung bình mỗi lượt phát, tính cả xem lại",
    numeric: true,
    value: latest("avg_watch_seconds"),
    render: (post) => formatSeconds(latest("avg_watch_seconds")(post)),
  },
  {
    key: "views_48h",
    title: "View 48 giờ",
    tip: "Lượt xem ở lần đo đầu tiên sau 48 giờ, để so các bài ở cùng tuổi",
    numeric: true,
    value: (post) => post.views_48h,
    render: (post) => formatNumber(post.views_48h),
  },
  {
    key: "times_median",
    title: "So với trung vị",
    tip: "View 48 giờ gấp mấy lần trung vị của Page (các bài 60 ngày qua)",
    numeric: true,
    value: (post) => post.times_median,
    render: (post) => <Times value={post.times_median} />,
  },
];

const ALL_KEYS = COLUMNS.map((column) => column.key);

function useRememberedColumns(): [Key[], (next: Key[]) => void] {
  const [keys, setKeys] = useState<Key[]>(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem(COLUMNS_KEY) ?? "null");
      if (Array.isArray(saved)) return ALL_KEYS.filter((key) => saved.includes(key));
    } catch {
      // A browser that refuses storage shows every column.
    }
    return ALL_KEYS;
  });
  function choose(next: Key[]) {
    setKeys(next);
    try {
      window.localStorage.setItem(COLUMNS_KEY, JSON.stringify(next));
    } catch {
      // A browser that refuses storage just forgets the choice.
    }
  }
  return [keys, choose];
}

type Sort = { key: Key; order: "ascend" | "descend" };

function sorted(posts: PageContentPost[], sort: Sort): PageContentPost[] {
  const column = COLUMNS.find((row) => row.key === sort.key)!;
  const sign = sort.order === "ascend" ? 1 : -1;
  return [...posts].sort((a, b) => {
    const x = column.value(a);
    const y = column.value(b);
    if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1;
    return (x < y ? -1 : x > y ? 1 : 0) * sign;
  });
}

function csvCell(value: string | number | null): string {
  if (value === null) return "";
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** The rows in their shown order and the shown columns, with the title first and the reel's link last. */
function downloadCsv(posts: PageContentPost[], columns: Column[], name: string) {
  const header = ["Tiêu đề", ...columns.map((column) => column.title), "Link reel"];
  const lines = posts.map((post) => [
    post.video.title,
    ...columns.map((column) => (column.key === "live_at" ? formatDateTime(post.live_at) : column.value(post))),
    post.url,
  ]);
  const text = [header, ...lines].map((line) => line.map(csvCell).join(",")).join("\r\n");
  // The BOM makes Excel read Vietnamese as UTF-8.
  const url = URL.createObjectURL(new Blob(["﻿", text], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

function RowMenu({ post, onRefresh }: { post: PageContentPost; onRefresh: (post: PageContentPost) => void }) {
  return (
    <Dropdown
      trigger={["click"]}
      menu={{
        items: [
          {
            key: "video",
            label: (
              <Link prefetch={false} href={`/videos/${post.video.id}`}>
                Mở video
              </Link>
            ),
          },
          {
            key: "reel",
            disabled: !post.url,
            label: post.url ? (
              <a href={post.url} target="_blank" rel="noreferrer">
                Mở reel trên Facebook
              </a>
            ) : (
              "Mở reel trên Facebook"
            ),
          },
          {
            key: "refresh",
            disabled: !post.can_refresh || post.pending,
            label: post.pending ? "Đang đo view…" : "Cập nhật view",
            onClick: () => onRefresh(post),
          },
        ],
      }}
    >
      <Button type="text" size="small" icon={<EllipsisOutlined />} aria-label="Thao tác với bài" />
    </Dropdown>
  );
}

/** The dashboard's "Nội dung" tab, like Facebook's content library: every post the app made to the Page that went
 * live in the period, with its latest numbers. */
export default function ContentLibrary({ pageId, days }: { pageId: string; days: number }) {
  const { message } = App.useApp();
  const [data, setData] = useState<PageContent | null>(null);
  const [shown, setShown] = useRememberedColumns();
  // The sort and page are in the address beside the dashboard's tab.
  const [sortKey, setSortKey] = useUrlChoice<Key>("sort", "live_at", ALL_KEYS);
  const [sortOrder, setSortOrder] = useUrlChoice<Sort["order"]>("order", "descend", ["ascend"]);
  const sort: Sort = useMemo(() => ({ key: sortKey, order: sortOrder }), [sortKey, sortOrder]);
  const setSort = (next: Sort) => {
    setSortKey(next.key);
    setSortOrder(next.order);
  };
  const tablePage = useUrlPage();

  // `quiet` for the refreshes: an api that is down is said once, on opening, not every minute.
  const load = useCallback(
    async (quiet = false) => {
      try {
        setData(await api<PageContent>(`/fanpages/${pageId}/content?days=${days}`));
      } catch (err) {
        if (!quiet) message.error(errorMessage(err));
      }
    },
    [pageId, days, message],
  );
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount and on a new period; state is set only after the request answers
    void load();
  }, [load]);
  usePolling(() => load(true), REFRESH_MS);

  // While a reading waits for the worker, ask again every few seconds until it has run.
  const pending = data?.posts.some((post) => post.pending) ?? false;
  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(() => void load(), 4000);
    return () => clearTimeout(timer);
  }, [pending, data, load]);

  async function refresh(post: PageContentPost) {
    try {
      await api(`/posts/${post.id}/metrics`, "POST");
      message.success("Đã gửi yêu cầu đo view, số mới sẽ có sau ít giây");
      await load();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  const columns = COLUMNS.filter((column) => shown.includes(column.key));
  const rows = useMemo(() => (data ? sorted(data.posts, sort) : []), [data, sort]);

  const tableColumns: TableColumnsType<PageContentPost> = [
    {
      key: "video",
      title: "Bài đăng",
      fixed: "left",
      width: 280,
      render: (_, post) => (
        <Flex gap={10} align="center" style={{ minWidth: 0 }}>
          <VideoThumbnail name={post.video.title} url={post.video.thumbnail_url} width={32} />
          <Typography.Text ellipsis={{ tooltip: post.video.title }} style={{ minWidth: 0 }}>
            <Link prefetch={false} href={`/videos/${post.video.id}`}>
              {post.video.title}
            </Link>
          </Typography.Text>
        </Flex>
      ),
    },
    ...columns.map((column) => ({
      key: column.key,
      dataIndex: column.key,
      title: column.tip ? (
        <Tooltip title={column.tip}>
          <span style={{ whiteSpace: "nowrap" }}>{column.title}</span>
        </Tooltip>
      ) : (
        <span style={{ whiteSpace: "nowrap" }}>{column.title}</span>
      ),
      align: column.numeric ? ("right" as const) : undefined,
      sorter: true,
      sortOrder: sort.key === column.key ? sort.order : null,
      sortDirections: ["descend", "ascend", "descend"] as ("descend" | "ascend")[],
      showSorterTooltip: false,
      render: (_: unknown, post: PageContentPost) => (
        <span style={column.numeric ? { fontVariantNumeric: "tabular-nums" } : undefined}>{column.render(post)}</span>
      ),
    })),
    {
      key: "menu",
      fixed: "right",
      width: 48,
      render: (_, post) => <RowMenu post={post} onRefresh={refresh} />,
    },
  ];

  function onChange(_: TablePaginationConfig, __: unknown, sorter: SorterResult<PageContentPost> | unknown) {
    const { columnKey, order } = sorter as SorterResult<PageContentPost>;
    if (columnKey && order) setSort({ key: columnKey as Key, order });
  }

  const median = data?.median;
  return (
    <Card
      size="small"
      title={data ? `${data.posts.length} bài app đăng trong ${data.days} ngày` : "Nội dung"}
      extra={
        <Flex gap={8}>
          <Popover
            trigger="click"
            placement="bottomRight"
            title="Cột hiện trong bảng"
            content={
              <Checkbox.Group<Key>
                value={shown}
                onChange={(next) => setShown(ALL_KEYS.filter((key) => next.includes(key)))}
                style={{ display: "flex", flexDirection: "column", gap: 4 }}
                options={COLUMNS.map((column) => ({ value: column.key, label: column.title }))}
              />
            }
          >
            <Button size="small" icon={<SettingOutlined />}>
              Cột
            </Button>
          </Popover>
          <Button
            size="small"
            icon={<DownloadOutlined />}
            disabled={rows.length === 0}
            onClick={() => downloadCsv(rows, columns, `noi-dung-page-${pageId}-${days}-ngay.csv`)}
          >
            Xuất CSV
          </Button>
        </Flex>
      }
    >
      <Flex vertical gap={8}>
        <Table<PageContentPost>
          data-testid="content-table"
          rowKey="id"
          size="small"
          loading={data === null}
          dataSource={rows}
          columns={tableColumns}
          onChange={onChange}
          pagination={rows.length > 50 ? { pageSize: 50, showSizeChanger: false, ...tablePage } : false}
          scroll={{ x: "max-content" }}
          locale={{
            emptyText: <EmptyState description={`Chưa có bài nào app đăng lên Page này trong ${days} ngày.`} />,
          }}
        />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Số ở lần đo mới nhất của mỗi bài (bấm “Cập nhật view” ở ⋯ để đo lại); bài đăng ngoài app không có ở đây.{" "}
          {median && median.samples >= median.min_samples && median.views !== null
            ? `Trung vị view 48 giờ của Page: ${formatNumber(median.views)} (${median.samples} bài).`
            : `Cần ít nhất ${median?.min_samples ?? 5} bài có view 48 giờ để so với trung vị.`}
        </Typography.Text>
      </Flex>
    </Card>
  );
}
