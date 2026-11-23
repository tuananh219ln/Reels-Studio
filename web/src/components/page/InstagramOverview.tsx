"use client";

import DailyChart from "@/components/page/DailyChart";
import { FigureTile, TileRow, formatNumber } from "@/components/page/Figures";
import { ApiError, api, errorMessage, type InstagramDashboard } from "@/lib/api";
import { usePolling } from "@/lib/polling";
import { Alert, App, Card, Flex, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

const REFRESH_MS = 60_000;

/** The "Tổng quan" of a Page's Instagram account, laid out like the Facebook one: four figures against the period
 * before, the views day by day, and what Instagram could not give. The numbers are read at each Page check with
 * `instagram_manage_insights`; without it the page says so, with the way to fix it. */
export default function InstagramOverview({ pageId, days }: { pageId: number; days: number }) {
  const { message } = App.useApp();
  const [data, setData] = useState<InstagramDashboard | null>(null);

  const load = useCallback(
    async (quiet = false) => {
      try {
        setData(await api<InstagramDashboard>(`/fanpages/${pageId}/instagram-dashboard?days=${days}`));
      } catch (err) {
        if (!quiet && !(err instanceof ApiError && err.status === 404)) message.error(errorMessage(err));
      }
    },
    [pageId, days, message],
  );
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount and on a new period; state is set only after the request answers
    void load();
  }, [load]);
  usePolling(() => load(true), REFRESH_MS);

  if (data === null) return <Card loading />;
  const { totals } = data;
  return (
    <Flex vertical gap={12} data-testid="instagram-overview">
      {data.insights_error && (
        <Alert
          type="warning"
          showIcon
          data-testid="instagram-insights-error"
          title={data.insights_error}
          description="Chủ Page dán token mới ở nút “Dán token mới” (trên thẻ Page ở Quản lý kênh), token cần có quyền instagram_manage_insights."
        />
      )}
      <TileRow>
        <FigureTile
          title="Lượt xem"
          figure={totals.views}
          days={data.days}
          tip="Số lần Reel và bài của tài khoản được xem"
        />
        <FigureTile
          title="Tiếp cận"
          figure={totals.reach}
          days={data.days}
          tip="Số tài khoản đã thấy nội dung, Instagram ước tính"
        />
        <FigureTile
          title="Tương tác"
          figure={totals.interactions}
          days={data.days}
          tip="Thích, bình luận, chia sẻ và lưu"
        />
        <FigureTile
          title="Người theo dõi mới"
          figure={totals.follows}
          days={data.days}
          note={`Hiện có ${formatNumber(data.followers)}`}
        />
      </TileRow>
      <Card size="small" title="Lượt xem theo ngày">
        <DailyChart
          label="Lượt xem"
          days={data.series.map((row) => row.day)}
          values={data.series.map((row) => row.views)}
          format={formatNumber}
          testId="instagram-chart"
          emptyText={`Chưa có số liệu trong ${data.days} ngày: tool đọc số liệu Instagram ở mỗi lần kiểm tra token`}
        />
      </Card>
      <Typography.Text type="secondary" style={{ fontSize: 13 }}>
        Số do Instagram tính và có thể trễ tới 48 giờ, nên vài ngày gần nhất còn được cập nhật. Chỉ có những số
        Instagram cho đọc.
      </Typography.Text>
    </Flex>
  );
}
