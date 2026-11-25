"use client";
import { formatCount } from "@/lib/format";
import { FanpageMenu, TokenInput, TokenModal } from "@/components/actions/FanpageActions";

import { COLORS } from "@/app/theme";
import EmptyState from "@/components/EmptyState";
import FormDrawer from "@/components/FormDrawer";
import { useMe } from "@/components/MeContext";
import { FollowerGain, MiniFigure } from "@/components/page/Figures";
import PageChannels from "@/components/page/PageChannels";
import PageHeader from "@/components/PageHeader";
import StatusText from "@/components/StatusText";
import WhoseFilter from "@/components/WhoseFilter";
import {
  api,
  errorMessage,
  formatDateTime,
  type AffiliateAccount,
  type Fanpage,
  type FanpageChoice,
  type QueueOverview,
  type QueuePage,
  type YouTubeConnection,
} from "@/lib/api";
import { useFreshenOnOpen } from "@/lib/freshen";
import { usePolling } from "@/lib/polling";
import { useUrlChoice } from "@/lib/urlState";
import { DeleteOutlined, FacebookOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { App, Avatar, Button, Card, Checkbox, Collapse, Flex, Popconfirm, Space, Tooltip, Typography } from "antd";
import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";

const QUEUE_REFRESH_MS = 30_000;
const number = formatCount;
const count = (value: number | null) => (value === null ? "—" : number(value));

/** Broken Pages first, so the one that needs a member is at the top. */
function byNeed(a: Fanpage, b: Fanpage): number {
  return Number(Boolean(b.check.error)) - Number(Boolean(a.check.error)) || a.name.localeCompare(b.name, "vi");
}

/** The worker's last check of the Page's token: works, broken, or waiting for the worker. */
function StatusTag({ row }: { row: Fanpage }) {
  const { check } = row;
  if (check.pending) return <StatusText tone="active">Đang kiểm tra…</StatusText>;
  if (check.error) return <StatusText tone="danger">Lỗi kết nối</StatusText>;
  if (check.checked_at) return <StatusText tone="success">Hoạt động</StatusText>;
  return <StatusText tone="idle">Chưa kiểm tra</StatusText>;
}

/** One line on how the Page posts on a schedule; the whole of it is on the Page's "Lịch đăng" tab. */
function ScheduleLine({ page }: { page: QueuePage }) {
  const parts = [
    page.topic ? `Nhóm “${page.topic.name}”` : "Chưa gắn nhóm chủ đề",
    page.post_times.length ? `đăng ${page.post_times.join(", ")}` : "chưa có giờ đăng",
    `${page.items.length} video trong hàng chờ`,
  ];
  return (
    <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="page-schedule-line">
      {parts.join(", ")}
    </Typography.Text>
  );
}

/** A Page in use, compact: who it is, whether its token works, its numbers, a line on how it posts on a schedule, and
 * what a member can do with it. A click anywhere else opens its dashboard. */
function PageCard({
  row,
  accounts,
  youtube,
  queue,
  onRows,
  onToken,
}: {
  row: Fanpage;
  accounts: AffiliateAccount[];
  youtube: YouTubeConnection[];
  queue: QueueOverview | null;
  onRows: (rows: Fanpage[]) => void;
  onToken: (row: Fanpage) => void;
}) {
  const scheduled = queue?.pages.find((page) => page.id === row.id);
  const dashboard = `/fanpages/${row.id}`;
  const { message } = App.useApp();
  const { check, insights } = row;
  const week = insights.last_7_days;

  async function call(path: string, method: "POST" | "PATCH", body?: object) {
    try {
      onRows(await api<Fanpage[]>(path, method, body));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  return (
    <Card
      size="small"
      hoverable
      className="stretch-host"
      data-testid="fanpage-card"
      style={{ height: "100%", borderColor: check.error ? COLORS.primaryBorder : undefined }}
      styles={{ body: { display: "flex", flexDirection: "column", gap: 10, height: "100%" } }}
    >
      <Flex gap={10} align="center">
        {/* The Page's Facebook picture; its initial while there is none or the link has expired (antd falls back). */}
        <Avatar
          size={32}
          src={row.picture ?? undefined}
          alt={`Ảnh đại diện ${row.name}`}
          style={{ background: COLORS.primaryBg, color: COLORS.primary, flex: "none" }}
        >
          {row.name.trim().charAt(0).toUpperCase() || <FacebookOutlined />}
        </Avatar>
        <Flex vertical style={{ minWidth: 0, flex: 1 }}>
          <Typography.Text strong ellipsis>
            <Link prefetch={false} href={dashboard} className="stretched-link">
              {row.name}
            </Link>
          </Typography.Text>
          {/* The status on its own line, so neither it nor the ID is cut off on a narrow card. */}
          <Flex gap={8} align="center" style={{ minWidth: 0 }}>
            <span style={{ flex: "none", whiteSpace: "nowrap" }}>
              <StatusTag row={row} />
            </span>
            <Typography.Text type="secondary" style={{ fontSize: 12, minWidth: 0 }} ellipsis>
              ID {row.page_id}, token …{row.token_tail}
            </Typography.Text>
          </Flex>
        </Flex>
        <FanpageMenu
          row={row}
          onToken={() => onToken(row)}
          onChanged={async () => onRows(await api<Fanpage[]>("/fanpages"))}
        />
      </Flex>

      {check.error && (
        <Flex
          gap={8}
          align="center"
          style={{ background: COLORS.primaryBg, borderRadius: 8, padding: "6px 10px" }}
          data-testid="fanpage-error"
        >
          <Typography.Text type="danger" style={{ fontSize: 12, flex: 1 }}>
            {check.error}
            {row.scheduled_posts > 0 && `, ${row.scheduled_posts} bài hẹn giờ bị ảnh hưởng`}
          </Typography.Text>
          <Button size="small" onClick={() => onToken(row)}>
            Dán token mới
          </Button>
        </Flex>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 8 }}>
        <MiniFigure
          label="Theo dõi"
          value={count(check.followers)}
          note={<FollowerGain gain={check.followers_this_week} />}
        />
        <MiniFigure label="Lượt xem" value={count(week.views)} />
        <MiniFigure label="Tiếp cận" value={count(week.reach)} />
        <MiniFigure label="Tương tác" value={count(week.engagements)} />
      </div>
      {insights.error && (
        <Typography.Text type="warning" style={{ fontSize: 12 }}>
          {insights.error}
        </Typography.Text>
      )}
      {row.alerts.map((alert) => (
        // Views fell by half or more against the week before: said in words, with both numbers, on the platform's side.
        <StatusText key={alert.platform} tone="warning" data-testid="fanpage-trend-alert">
          Lượt xem {alert.platform === "facebook" ? "Facebook" : "Instagram"} giảm{" "}
          {Math.round(Math.abs(alert.change) * 100)}% so với tuần trước ({count(alert.current)} so với{" "}
          {count(alert.previous)})
        </StatusText>
      ))}
      <PageChannels row={row} accounts={accounts} youtube={youtube} onRows={onRows} />
      {scheduled && <ScheduleLine page={scheduled} />}

      <Flex justify="space-between" align="center" gap={8} style={{ marginTop: "auto" }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }} ellipsis>
          Số liệu 7 ngày, {check.checked_at ? `kiểm tra ${formatDateTime(check.checked_at)}` : "chưa kiểm tra"}
          {row.scheduled_posts > 0 && !check.error && `, ${row.scheduled_posts} bài hẹn giờ`}
        </Typography.Text>
        <Space size={0}>
          <Tooltip title="Kiểm tra ngay">
            <Button
              size="small"
              type="text"
              icon={<ReloadOutlined spin={check.pending} />}
              aria-label="Kiểm tra ngay"
              disabled={check.pending}
              onClick={() => call(`/fanpages/${row.id}/check`, "POST")}
            />
          </Tooltip>
        </Space>
      </Flex>
    </Card>
  );
}

/** Pages no longer used, folded away: "Dùng lại", or "Xóa" for one that never had a post. */
function StoppedPages({ rows, onRows }: { rows: Fanpage[]; onRows: (rows: Fanpage[]) => void }) {
  const { message } = App.useApp();
  const { me } = useMe();
  if (rows.length === 0) return null;

  async function call(path: string, method: "PATCH" | "DELETE", body?: object) {
    try {
      onRows(await api<Fanpage[]>(path, method, body));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  return (
    <Collapse
      items={[
        {
          key: "stopped",
          label: `Đã ngừng dùng (${rows.length})`,
          children: (
            <Flex vertical gap={0}>
              {rows.map((row, index) => (
                <Flex
                  key={row.id}
                  justify="space-between"
                  align="center"
                  gap={8}
                  wrap
                  data-testid="stopped-fanpage"
                  style={{ padding: "10px 0", borderTop: index ? `1px solid ${COLORS.border}` : undefined }}
                >
                  <Flex vertical style={{ minWidth: 0 }}>
                    <Typography.Text>{row.name}</Typography.Text>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      ID {row.page_id}, {row.posts ? `${row.posts} bài đăng` : "chưa đăng bài nào"}, ngừng{" "}
                      {formatDateTime(row.updated_at)}
                      {row.updated_by ? ` bởi ${row.updated_by}` : ""}
                    </Typography.Text>
                  </Flex>
                  {row.owner?.id === me.id && (
                    <Space size={4}>
                      <Button size="small" onClick={() => call(`/fanpages/${row.id}`, "PATCH", { active: true })}>
                        Dùng lại
                      </Button>
                      {row.posts ? (
                        <Tooltip title="Page đã có bài đăng nên được giữ lại để xem lịch sử">
                          <Button size="small" icon={<DeleteOutlined />} disabled>
                            Xóa
                          </Button>
                        </Tooltip>
                      ) : (
                        <Popconfirm
                          title={`Xóa ${row.name}?`}
                          description="Xóa cả token và số liệu đã lưu. Muốn dùng lại phải thêm Page lại từ đầu."
                          okText="Xóa"
                          okButtonProps={{ danger: true }}
                          cancelText="Huỷ"
                          onConfirm={() => call(`/fanpages/${row.id}`, "DELETE")}
                        >
                          <Button size="small" danger icon={<DeleteOutlined />}>
                            Xóa
                          </Button>
                        </Popconfirm>
                      )}
                    </Space>
                  )}
                </Flex>
              ))}
            </Flex>
          ),
        },
      ]}
    />
  );
}

/** Paste a token, see the Pages it manages, choose which to connect. */
function AddModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: (rows: Fanpage[]) => void;
}) {
  const { message } = App.useApp();
  const [token, setToken] = useState("");
  const [pages, setPages] = useState<FanpageChoice[] | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function lookup() {
    setBusy(true);
    try {
      const found = (await api<{ pages: FanpageChoice[] }>("/fanpages/lookup", "POST", { token })).pages;
      setPages(found);
      const usable = found.filter((page) => page.can_post);
      setChosen(usable.length === 1 ? [usable[0].page_id] : []);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    try {
      onSaved(await api<Fanpage[]>("/fanpages", "POST", { token, page_ids: chosen }));
      onClose();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title="Thêm Fanpage"
      open={open}
      onClose={onClose}
      destroyOnHidden
      afterClose={() => {
        setToken("");
        setPages(null);
        setChosen([]);
      }}
      okText={pages ? "Lưu" : "Kiểm tra token"}
      cancelText="Huỷ"
      confirmLoading={busy}
      okButtonProps={{ disabled: pages ? chosen.length === 0 : !token.trim() }}
      onOk={pages ? save : lookup}
    >
      <Flex vertical gap={12}>
        {/* What the token needs is only read here, while adding a Page. */}
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          Dán token của một System User trong Business Manager đã được gán Page, có quyền <code>pages_show_list</code>,{" "}
          <code>pages_read_engagement</code>, <code>pages_manage_posts</code>, <code>pages_manage_engagement</code>,{" "}
          <code>pages_read_user_content</code> và <code>read_insights</code>; muốn xem số liệu Instagram của Page, thêm{" "}
          <code>instagram_manage_insights</code>. Token được lưu mã hoá, không bao giờ hiện lại.
        </Typography.Paragraph>
        <TokenInput
          value={token}
          onChange={(value) => {
            setToken(value);
            setPages(null);
          }}
        />
        {pages && (
          <Checkbox.Group
            value={chosen}
            onChange={(values) => setChosen(values as string[])}
            style={{ display: "flex", flexDirection: "column", gap: 6 }}
            options={pages.map((page) => ({
              value: page.page_id,
              disabled: !page.can_post,
              label: page.can_post ? `${page.name} (${page.page_id})` : `${page.name} (token không có quyền đăng)`,
            }))}
          />
        )}
      </Flex>
    </FormDrawer>
  );
}

export default function FanpagesPage() {
  // "Trang của tôi / Tất cả" is in the address, which a static page only knows in the browser.
  return (
    <Suspense fallback={null}>
      <Fanpages />
    </Suspense>
  );
}

function Fanpages() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<Fanpage[] | null>(null);
  // "Trang của tôi" or "Tất cả"; null until chosen (the default follows whether the member owns a Page).
  const [whose, setWhose] = useUrlChoice<"mine" | "all" | null>("whose", null, ["mine", "all"]);
  const [adding, setAdding] = useState(false);
  const [replacing, setReplacing] = useState<Fanpage | null>(null);
  const [accounts, setAccounts] = useState<AffiliateAccount[]>([]);
  const [youtube, setYouTube] = useState<YouTubeConnection[]>([]);
  const [queue, setQueue] = useState<QueueOverview | null>(null);

  useEffect(() => {
    // Without them a Page shows its owner but offers no account to choose.
    api<AffiliateAccount[]>("/affiliate-accounts").then(setAccounts, () => undefined);
    api<YouTubeConnection[]>("/youtube/connections").then(setYouTube, () => undefined);
  }, []);

  const load = useCallback(async () => {
    try {
      setRows(await api<Fanpage[]>("/fanpages"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void load();
  }, [load]);
  // The queues change as the worker schedules their videos: read them again now and then.
  const loadQueue = useCallback(() => api<QueueOverview>("/queue").then(setQueue, () => undefined), []);
  useEffect(() => {
    void loadQueue();
  }, [loadQueue, rows]);
  usePolling(loadQueue, QUEUE_REFRESH_MS);

  // Pages not checked lately are checked again on opening, without pressing "Kiểm tra ngay" on each.
  useFreshenOnOpen("/fanpages/freshen", load);

  // While a check waits for the worker, ask again every few seconds until it has answered.
  const pending = rows?.some((row) => row.active && row.check.pending) ?? false;
  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(() => void load(), 4000);
    return () => clearTimeout(timer);
  }, [pending, rows, load]);

  // "Trang của tôi" by default for a member who owns a Page in use; "Tất cả" otherwise or once chosen.
  const ownsOne = (rows ?? []).some((row) => row.active && row.mine);
  const showing = whose ?? (ownsOne ? "mine" : "all");
  const shown = (rows ?? []).filter((row) => showing === "all" || row.mine);
  const inUse = shown.filter((row) => row.active).sort(byNeed);
  const stopped = shown.filter((row) => !row.active);
  const broken = inUse.filter((row) => row.check.error).length;

  return (
    <>
      <PageHeader
        title="Quản lý kênh"
        actions={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>
            Thêm Fanpage
          </Button>
        }
        description="Các kênh đội đăng bài: số liệu 7 ngày, nơi mỗi Page đăng và lịch đăng. Tool tự kiểm tra token mỗi 12 giờ."
      />
      <Flex vertical gap={16}>
        {rows !== null && rows.length > 0 && (
          <Flex gap={8} wrap align="center">
            <WhoseFilter
              label="Trang nào"
              value={showing}
              onChange={setWhose}
              mineLabel="Trang của tôi"
              allLabel="Tất cả"
              mine={rows.filter((row) => row.mine).length}
              all={rows.length}
            />
            <StatusText tone="success">{inUse.length} đang dùng</StatusText>
            {broken > 0 && <StatusText tone="danger">{broken} lỗi kết nối</StatusText>}
            {stopped.length > 0 && <StatusText tone="idle">{stopped.length} ngừng dùng</StatusText>}
          </Flex>
        )}
        {rows === null ? (
          <Card loading />
        ) : rows.length === 0 ? (
          // Named apart from the header's "Thêm Fanpage", so no two buttons share a name.
          <Card>
            <EmptyState
              description="Chưa kết nối Fanpage nào"
              action={
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>
                  Kết nối Page đầu tiên
                </Button>
              }
            />
          </Card>
        ) : inUse.length === 0 ? (
          <Card>
            <EmptyState
              description={showing === "mine" ? "Bạn chưa có Fanpage nào đang dùng" : "Không có Fanpage nào đang dùng"}
              action={showing === "mine" && <Button onClick={() => setWhose("all")}>Xem tất cả Page</Button>}
            />
          </Card>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))",
              gap: 12,
            }}
          >
            {inUse.map((row) => (
              <PageCard
                key={row.id}
                row={row}
                accounts={accounts}
                youtube={youtube}
                queue={queue}
                onRows={setRows}
                onToken={setReplacing}
              />
            ))}
          </div>
        )}
        <StoppedPages rows={stopped} onRows={setRows} />
      </Flex>
      <AddModal open={adding} onClose={() => setAdding(false)} onSaved={setRows} />
      <TokenModal row={replacing} onClose={() => setReplacing(null)} onSaved={setRows} />
    </>
  );
}
