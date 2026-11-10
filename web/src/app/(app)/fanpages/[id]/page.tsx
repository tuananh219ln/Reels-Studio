"use client";

import { ArrowLeftOutlined, ReloadOutlined } from "@ant-design/icons";
import { App, Button, Card, Empty, Flex, Result, Segmented, Spin, Switch, Tabs, Typography } from "antd";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import PageHeader from "@/components/PageHeader";
import PageQueueSection from "@/components/PageQueueSection";
import StatusText from "@/components/StatusText";
import VideoThumbnail from "@/components/VideoThumbnail";
import ContentLibrary from "@/components/page/ContentLibrary";
import DailyChart, { shortDay } from "@/components/page/DailyChart";
import { FigureTile, TileRow, formatNumber, formatSeconds } from "@/components/page/Figures";
import { ApiError, api, errorMessage, formatDateTime, type PageDashboard, type QueueOverview } from "@/lib/api";
import { useFreshenOnOpen } from "@/lib/freshen";
import { usePolling } from "@/lib/polling";
import { keepOnlyInAddress, useUrlChoice } from "@/lib/urlState";

const PERIODS = [7, 28, 90] as const;
type Days = (typeof PERIODS)[number];
const REFRESH_MS = 60_000;
const QUEUE_REFRESH_MS = 30_000;
// The "Đã lên lịch" strip on Tổng quan names the first few; "Lịch đăng" lists the whole week.
const STRIP = 6;

const APPROXIMATE =
  "Cộng từ lần đo mới nhất của các bài app đăng trong khoảng này, nên gần đúng: số của một bài còn tăng sau ngày đăng, " +
  "và bài đăng ngoài app không được tính.";

const vietnamDay = new Intl.DateTimeFormat("vi-VN", {
  timeZone: "Asia/Ho_Chi_Minh",
  weekday: "short",
  day: "2-digit",
  month: "2-digit",
});
const vietnamTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Ho_Chi_Minh",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** The token's last check, as on the Page's card. */
function TokenStatus({ data }: { data: PageDashboard }) {
  const { check } = data.page;
  return (
    <Card size="small" title="Kết nối" data-testid="token-status">
      <Flex vertical gap={4}>
        {check.pending ? (
          <StatusText tone="active">Đang kiểm tra…</StatusText>
        ) : check.error ? (
          <StatusText tone="danger">Lỗi kết nối</StatusText>
        ) : check.checked_at ? (
          <StatusText tone="success">Hoạt động</StatusText>
        ) : (
          <StatusText tone="idle">Chưa kiểm tra</StatusText>
        )}
        {check.error && (
          <Typography.Text type="danger" style={{ fontSize: 12 }}>
            {check.error}. Dán token mới ở Quản lý Page.
          </Typography.Text>
        )}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Token …{data.page.token_tail},{" "}
          {check.checked_at ? `kiểm tra ${formatDateTime(check.checked_at)}` : "chưa kiểm tra"}
        </Typography.Text>
        {data.page.insights_error && (
          <Typography.Text type="warning" style={{ fontSize: 12 }}>
            Số liệu Page: {data.page.insights_error}
          </Typography.Text>
        )}
      </Flex>
    </Card>
  );
}

/** The newest post the app made to the Page, with its numbers at the last reading. */
function LatestPost({ data }: { data: PageDashboard }) {
  const post = data.latest_post;
  return (
    <Card size="small" title="Bài đăng mới nhất" data-testid="latest-post">
      {post ? (
        <Flex gap={12}>
          <VideoThumbnail name={post.video.title} url={post.video.thumbnail_url} width={56} />
          <Flex vertical gap={4} style={{ minWidth: 0, flex: 1 }}>
            <Typography.Text strong ellipsis>
              <Link prefetch={false} href={`/videos/${post.video.id}`}>
                {post.video.title}
              </Link>
            </Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Lên lúc {formatDateTime(post.live_at)}
            </Typography.Text>
            {post.numbers ? (
              <>
                <Flex gap={16} wrap style={{ fontSize: 13 }}>
                  <span>Lượt xem {formatNumber(post.numbers.views)}</span>
                  <span>Tiếp cận {formatNumber(post.numbers.reach)}</span>
                  <span>Cảm xúc {formatNumber(post.numbers.reactions)}</span>
                  <span>Bình luận {formatNumber(post.numbers.comments)}</span>
                  <span>Chia sẻ {formatNumber(post.numbers.shares)}</span>
                  <span>Xem TB {formatSeconds(post.numbers.avg_watch_seconds)}</span>
                </Flex>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Đo lúc {formatDateTime(post.numbers.measured_at)}
                </Typography.Text>
              </>
            ) : (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                Chưa đọc được số của bài này.
              </Typography.Text>
            )}
          </Flex>
        </Flex>
      ) : (
        <Typography.Text type="secondary">Chưa có bài nào app đăng lên Page này.</Typography.Text>
      )}
    </Card>
  );
}

type Slot = { at: string; post: PageDashboard["upcoming"]["posts"][number] | null };

/** The week's scheduled posts and free posting times, in time order. */
function slotsOf(data: PageDashboard): Slot[] {
  const slots: Slot[] = [
    ...data.upcoming.posts.map((post) => ({ at: post.scheduled_at, post })),
    ...data.upcoming.free_slots.map((at) => ({ at, post: null })),
  ];
  return slots.sort((a, b) => a.at.localeCompare(b.at));
}

function SlotRow({ slot }: { slot: Slot }) {
  const when = new Date(slot.at);
  return (
    <Flex gap={10} align="center" data-testid={slot.post ? "scheduled-post" : "free-slot"}>
      <Typography.Text style={{ width: 92, flex: "none", fontSize: 13 }}>
        {vietnamDay.format(when)} {vietnamTime.format(when)}
      </Typography.Text>
      {slot.post ? (
        <>
          <VideoThumbnail name={slot.post.video.title} url={slot.post.video.thumbnail_url} width={24} />
          <Typography.Text ellipsis style={{ fontSize: 13, flex: 1, minWidth: 0 }}>
            <Link prefetch={false} href={`/videos/${slot.post.video.id}`}>
              {slot.post.video.title}
            </Link>
          </Typography.Text>
          <StatusText tone="waiting">{slot.post.status === "pending" ? "Đang đăng" : "Đã hẹn giờ"}</StatusText>
        </>
      ) : (
        <Typography.Text type="secondary" style={{ fontSize: 13 }}>
          Khung trống
        </Typography.Text>
      )}
    </Flex>
  );
}

function Scheduled({ data, limit }: { data: PageDashboard; limit?: number }) {
  const slots = slotsOf(data);
  const shown = limit ? slots.slice(0, limit) : slots;
  return (
    <Card size="small" title="Đã lên lịch, 7 ngày tới" data-testid="scheduled-strip">
      {slots.length === 0 ? (
        <Typography.Text type="secondary">
          {data.upcoming.post_times.length === 0
            ? "Chưa có bài hẹn giờ, và Page chưa có giờ đăng: chọn nhóm chủ đề hoặc giờ riêng ở “Đăng theo lịch”."
            : "Không có bài hẹn giờ hay khung trống nào trong 7 ngày tới."}
        </Typography.Text>
      ) : (
        <Flex vertical gap={6}>
          {shown.map((slot) => (
            <SlotRow key={`${slot.at}-${slot.post?.id ?? "free"}`} slot={slot} />
          ))}
          {shown.length < slots.length && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Và {slots.length - shown.length} mục khác ở tab Lịch đăng.
            </Typography.Text>
          )}
        </Flex>
      )}
    </Card>
  );
}

type Metric = "views" | "reach" | "engagements" | "followers";

function series(data: PageDashboard, metric: Metric) {
  return {
    days: data.series.map((row) => row.day),
    values: data.series.map((row) => row[metric]),
  };
}

function Overview({ data }: { data: PageDashboard }) {
  const { totals, days } = data;
  return (
    <Flex vertical gap={12}>
      <TileRow>
        <FigureTile title="Lượt xem" figure={totals.views} days={days} />
        <FigureTile title="Tiếp cận" figure={totals.reach} days={days} />
        <FigureTile title="Tương tác" figure={totals.engagements} days={days} />
        <FigureTile
          title="Người theo dõi mới"
          figure={totals.followers_gain}
          days={days}
          note={`Hiện có ${formatNumber(data.followers)}`}
        />
      </TileRow>
      <Card size="small" title="Lượt xem theo ngày">
        <DailyChart label="Lượt xem" {...series(data, "views")} format={formatNumber} testId="overview-chart" />
      </Card>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 360px), 1fr))", gap: 12 }}>
        <LatestPost data={data} />
        <Scheduled data={data} limit={STRIP} />
      </div>
      <TokenStatus data={data} />
    </Flex>
  );
}

function Views({ data }: { data: PageDashboard }) {
  const { totals, days } = data;
  const [metric, setMetric] = useState<"views" | "reach">("views");
  const [activity, setActivity] = useState(true);
  return (
    <Flex vertical gap={12}>
      <TileRow>
        <FigureTile title="Lượt xem" figure={totals.views} days={days} tip="Số lần nội dung của Page được xem" />
        <FigureTile
          title="Tiếp cận"
          figure={totals.reach}
          days={days}
          tip="Số người đã thấy nội dung, Facebook ước tính"
        />
        <FigureTile
          title="Thời gian xem TB"
          figure={data.post_numbers.avg_watch_seconds}
          days={days}
          format={formatSeconds}
          tip={`Mỗi lượt phát, tính theo lượt xem của các bài app đăng trong khoảng này. ${APPROXIMATE}`}
        />
      </TileRow>
      <Card
        size="small"
        title={
          <Segmented<"views" | "reach">
            size="small"
            value={metric}
            onChange={setMetric}
            options={[
              { value: "views", label: "Lượt xem" },
              { value: "reach", label: "Tiếp cận" },
            ]}
          />
        }
        extra={
          <Flex gap={6} align="center">
            <Switch size="small" checked={activity} onChange={setActivity} aria-label="Hoạt động đăng" />
            <Typography.Text style={{ fontSize: 13 }}>Hoạt động đăng</Typography.Text>
          </Flex>
        }
      >
        <DailyChart
          label={metric === "views" ? "Lượt xem" : "Tiếp cận"}
          {...series(data, metric)}
          format={formatNumber}
          posts={activity ? data.series.map((row) => row.posts) : undefined}
          testId="views-chart"
        />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {totals.posts.value ?? 0} bài app đăng trong {days} ngày.
        </Typography.Text>
      </Card>
    </Flex>
  );
}

function Engagement({ data }: { data: PageDashboard }) {
  const { totals, days, post_numbers: posts } = data;
  return (
    <Flex vertical gap={12}>
      <TileRow>
        <FigureTile
          title="Tương tác"
          figure={totals.engagements}
          days={days}
          tip="Cảm xúc, bình luận, chia sẻ và lượt bấm vào bài của Page, theo Page Insights"
        />
      </TileRow>
      <Card size="small" title="Tương tác theo ngày">
        <DailyChart
          label="Tương tác"
          {...series(data, "engagements")}
          format={formatNumber}
          testId="engagement-chart"
        />
      </Card>
      <Typography.Text type="secondary" style={{ fontSize: 13 }}>
        Chia theo loại, từ các bài app đăng trong khoảng này (gần đúng):
      </Typography.Text>
      <TileRow>
        <FigureTile title="Cảm xúc" figure={posts.reactions} days={days} tip={APPROXIMATE} />
        <FigureTile title="Bình luận" figure={posts.comments} days={days} tip={APPROXIMATE} />
        <FigureTile title="Chia sẻ" figure={posts.shares} days={days} tip={APPROXIMATE} />
      </TileRow>
    </Flex>
  );
}

function Audience({ data }: { data: PageDashboard }) {
  const { totals, days } = data;
  return (
    <Flex vertical gap={12}>
      <TileRow>
        <FigureTile
          title="Người theo dõi mới"
          figure={totals.followers_gain}
          days={days}
          tip="Số người theo dõi cuối khoảng trừ số đọc được gần nhất trước khoảng; đã trừ người bỏ theo dõi"
        />
        <Card size="small" style={{ height: "100%" }}>
          <Flex vertical gap={2}>
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              Người theo dõi hiện có
            </Typography.Text>
            <Typography.Text strong style={{ fontSize: 24, lineHeight: "32px" }} data-testid="followers-now">
              {formatNumber(data.followers)}
            </Typography.Text>
          </Flex>
        </Card>
      </TileRow>
      <Card size="small" title="Người theo dõi theo ngày">
        <DailyChart
          label="Người theo dõi"
          {...series(data, "followers")}
          format={formatNumber}
          emptyText="Chưa có số người theo dõi: tool đọc ở mỗi lần kiểm tra token"
          testId="followers-chart"
        />
      </Card>
    </Flex>
  );
}

function Schedule({
  data,
  queue,
  onQueue,
}: {
  data: PageDashboard;
  queue: QueueOverview | null;
  onQueue: (overview: QueueOverview) => void;
}) {
  const page = queue?.pages.find((row) => row.id === data.page.id);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 380px), 1fr))", gap: 12 }}>
      <Card size="small" title="Đăng theo lịch">
        {queue === null ? (
          <Spin />
        ) : page ? (
          <PageQueueSection page={page} overview={queue} onChanged={onQueue} />
        ) : (
          <Typography.Text type="secondary">Page đang ngừng dùng nên không đăng theo lịch.</Typography.Text>
        )}
      </Card>
      <Scheduled data={data} />
    </div>
  );
}

export default function FanpageDashboardPage() {
  // The period, tab and the content list's sort are in the address, which a static page only knows in the browser.
  return (
    <Suspense fallback={null}>
      <FanpageDashboard />
    </Suspense>
  );
}

function FanpageDashboard() {
  const { id } = useParams<{ id: string }>();
  const { message } = App.useApp();
  // The period and tab are in the address, so a reload or a shared link opens the same view.
  const [period, setPeriod] = useUrlChoice<"7" | "28" | "90">("days", "28", ["7", "90"]);
  const days = Number(period) as Days;
  const setDays = (next: Days) => setPeriod(String(next) as "7" | "28" | "90");
  const [data, setData] = useState<PageDashboard | null>(null);
  const [missing, setMissing] = useState(false);
  const [queue, setQueue] = useState<QueueOverview | null>(null);
  const [tab, setTabInAddress] = useUrlChoice<string>("tab", "overview");
  // A tab starts without the last tab's sort and page; the period stays.
  const setTab = (next: string) => {
    keepOnlyInAddress(period === "28" ? {} : { days: period });
    setTabInAddress(next);
  };

  const load = useCallback(async () => {
    try {
      setData(await api<PageDashboard>(`/fanpages/${id}/dashboard?days=${days}`));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setMissing(true);
      else message.error(errorMessage(err));
    }
  }, [id, days, message]);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount and on a new period; state is set only after the request answers
    void load();
  }, [load]);
  usePolling(load, REFRESH_MS);
  useFreshenOnOpen("/fanpages/freshen", load);

  const loadQueue = useCallback(() => api<QueueOverview>("/queue").then(setQueue, () => undefined), []);
  useEffect(() => {
    void loadQueue();
  }, [loadQueue]);
  usePolling(loadQueue, QUEUE_REFRESH_MS);

  // While a check waits for the worker, ask again every few seconds until it has answered.
  const pending = data?.page.check.pending ?? false;
  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(() => void load(), 4000);
    return () => clearTimeout(timer);
  }, [pending, data, load]);

  async function checkNow() {
    try {
      await api(`/fanpages/${id}/check`, "POST");
      await load();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  if (missing) {
    return (
      <Result
        status="404"
        title="Không tìm thấy Fanpage"
        extra={
          <Link prefetch={false} href="/fanpages">
            Về Quản lý Page
          </Link>
        }
      />
    );
  }

  return (
    <>
      <Link
        prefetch={false}
        href="/fanpages"
        aria-label="Quay lại Quản lý Page"
        style={{ display: "inline-block", marginBottom: 8, fontSize: 13 }}
      >
        <ArrowLeftOutlined /> Quản lý Page
      </Link>
      <PageHeader
        title={data?.page.name ?? "Fanpage"}
        actions={
          <>
            <Segmented<Days>
              value={days}
              onChange={setDays}
              aria-label="Khoảng thời gian"
              options={PERIODS.map((value) => ({ value, label: `${value} ngày` }))}
            />
            <Button
              icon={<ReloadOutlined spin={pending} />}
              disabled={pending || data?.page.active === false}
              onClick={checkNow}
            >
              Kiểm tra ngay
            </Button>
          </>
        }
        description={
          data && (
            <>
              Từ {shortDay(data.start)} đến {shortDay(data.end)} (giờ Việt Nam), mỗi số so với {data.days} ngày trước
              đó. Số của Page do Facebook tính theo ngày giờ Thái Bình Dương nên lệch giờ Việt Nam một chút; chỉ có
              những số Facebook cho đọc.
            </>
          )
        }
      />
      {data === null ? (
        <Card loading />
      ) : (
        <Flex vertical gap={12}>
          {data.series.every((row) => row.views === null && row.followers === null) && (
            <Card size="small">
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={`Chưa có số liệu trong ${data.days} ngày: tool đọc Page Insights và người theo dõi ở mỗi lần kiểm tra token`}
              />
            </Card>
          )}
          <Tabs
            activeKey={tab}
            onChange={setTab}
            items={tabs(data, queue, (overview) => {
              setQueue(overview);
              // A new group or posting times change the week's free times.
              void load();
            })}
          />
        </Flex>
      )}
    </>
  );
}

function tabs(data: PageDashboard, queue: QueueOverview | null, onQueue: (overview: QueueOverview) => void) {
  return [
    { key: "overview", label: "Tổng quan", children: <Overview data={data} /> },
    { key: "views", label: "Lượt xem", children: <Views data={data} /> },
    { key: "engagement", label: "Tương tác", children: <Engagement data={data} /> },
    { key: "audience", label: "Đối tượng", children: <Audience data={data} /> },
    { key: "content", label: "Nội dung", children: <ContentLibrary pageId={String(data.page.id)} days={data.days} /> },
    {
      key: "schedule",
      label: "Lịch đăng",
      children: <Schedule data={data} queue={queue} onQueue={onQueue} />,
    },
  ];
}
