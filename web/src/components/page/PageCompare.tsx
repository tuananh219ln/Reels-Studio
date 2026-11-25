"use client";

import EmptyState from "@/components/EmptyState";
import VideoTitleCell from "@/components/VideoTitleCell";
import { formatNumber } from "@/components/page/Figures";
import { api, errorMessage, formatDateTime, type PageCompare as Compare } from "@/lib/api";
import { usePolling } from "@/lib/polling";
import { App, Card, Flex, Segmented, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";

const REFRESH_MS = 60_000;
type Row = Compare["videos"][number];
type Side = NonNullable<Row["facebook"]>;

const METRICS = [
  { value: "views", label: "Lượt xem", noun: "lượt xem" },
  { value: "reach", label: "Tiếp cận", noun: "tiếp cận" },
  { value: "interactions", label: "Tương tác", noun: "tương tác" },
] as const;
type Metric = (typeof METRICS)[number]["value"];
// Remembered in this browser, like the columns of the "Nội dung" table.
const METRIC_KEY = "page-compare-metric";

function useRememberedMetric(): [Metric, (next: Metric) => void] {
  const [metric, setMetric] = useState<Metric>(() => {
    try {
      const saved = window.localStorage.getItem(METRIC_KEY);
      return METRICS.find((one) => one.value === saved)?.value ?? "views";
    } catch {
      return "views";
    }
  });
  function choose(next: Metric) {
    setMetric(next);
    try {
      window.localStorage.setItem(METRIC_KEY, next);
    } catch {
      // A browser that refuses storage just forgets the choice.
    }
  }
  return [metric, choose];
}

/** One platform's number of the chosen metric, with the other one worth a glance under it (interactions under views,
 * views under the rest). A platform the video is not on says so instead of showing a number. */
function Cell({ side, metric }: { side: Side | null; metric: Metric }) {
  if (side === null) return <Typography.Text type="secondary">Chưa đăng</Typography.Text>;
  const other: Metric = metric === "views" ? "interactions" : "views";
  const noun = METRICS.find((one) => one.value === other)!.noun;
  return (
    <Flex vertical align="flex-end" style={{ fontVariantNumeric: "tabular-nums" }}>
      <Typography.Text strong>{formatNumber(side[metric])}</Typography.Text>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {formatNumber(side[other])} {noun}
      </Typography.Text>
    </Flex>
  );
}

/** "So sánh": the same video on Facebook and Instagram side by side, so a member sees which platform a video suits.
 * Each platform's numbers are its own: Facebook counts plays, Instagram counts views, and neither is the other's. */
export default function PageCompare({ pageId, days }: { pageId: number; days: number }) {
  const { message } = App.useApp();
  const [data, setData] = useState<Compare | null>(null);
  const [metric, setMetric] = useRememberedMetric();

  const load = useCallback(
    async (quiet = false) => {
      try {
        setData(await api<Compare>(`/fanpages/${pageId}/compare?days=${days}`));
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

  const columns: ColumnsType<Row> = [
    {
      title: "Video",
      key: "video",
      width: 300,
      render: (_, row) => (
        <VideoTitleCell
          id={row.video.id}
          title={row.video.title}
          thumbnailUrl={row.video.thumbnail_url}
          sub={formatDateTime((row.facebook ?? row.instagram)!.live_at)}
        />
      ),
    },
    {
      title: "Facebook",
      key: "facebook",
      align: "right",
      width: 150,
      render: (_, row) => <Cell side={row.facebook} metric={metric} />,
    },
    {
      title: "Instagram",
      key: "instagram",
      align: "right",
      width: 150,
      render: (_, row) => <Cell side={row.instagram} metric={metric} />,
    },
  ];
  return (
    <Card size="small" styles={{ body: { padding: 0 } }} data-testid="page-compare">
      <Segmented<Metric>
        aria-label="Chỉ số so sánh"
        value={metric}
        onChange={setMetric}
        options={METRICS.map(({ value, label }) => ({ value, label }))}
        style={{ margin: "8px 12px" }}
      />
      <Table<Row>
        rowKey={(row) => row.video.id}
        size="middle"
        loading={data === null}
        dataSource={data?.videos ?? []}
        columns={columns}
        pagination={false}
        scroll={{ x: 620 }}
        locale={{ emptyText: <EmptyState description={`Chưa có video nào app đăng lên Page trong ${days} ngày`} /> }}
      />
      <Typography.Text type="secondary" style={{ display: "block", padding: "8px 16px", fontSize: 12 }}>
        Lượt xem của Facebook tính mọi lượt phát, của Instagram tính lượt xem Reel; tương tác là thích, bình luận và
        chia sẻ (Instagram thêm lưu). Hai nền tảng tính khác nhau nên so tương đối, không so từng con số.
      </Typography.Text>
    </Card>
  );
}
