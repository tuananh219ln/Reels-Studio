"use client";

import {
  BarChartOutlined,
  DeleteOutlined,
  FacebookOutlined,
  MoreOutlined,
  PlusOutlined,
  ReloadOutlined,
  StopOutlined,
} from "@ant-design/icons";
import {
  App,
  Avatar,
  Button,
  Card,
  Checkbox,
  Collapse,
  Dropdown,
  Empty,
  Flex,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  errorMessage,
  formatDateTime,
  type AffiliateAccount,
  type Fanpage,
  type FanpageChoice,
  type FanpageDay,
} from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { COLORS } from "@/app/theme";
import { useFreshenOnOpen } from "@/lib/freshen";
import FormDrawer from "@/components/FormDrawer";

const number = (value: number) => value.toLocaleString("vi-VN");
const count = (value: number | null) => (value === null ? "—" : number(value));
const pageUrl = (row: Fanpage) => `https://www.facebook.com/${row.page_id}`;

/** Broken Pages first, so the one that needs a member is at the top. */
function byNeed(a: Fanpage, b: Fanpage): number {
  return Number(Boolean(b.check.error)) - Number(Boolean(a.check.error)) || a.name.localeCompare(b.name, "vi");
}

/** The worker's last check of the Page's token: works, broken, or waiting for the worker. */
function StatusTag({ row }: { row: Fanpage }) {
  const { check } = row;
  if (check.pending) return <Tag color="processing">Đang kiểm tra…</Tag>;
  if (check.error) return <Tag color="error">Lỗi kết nối</Tag>;
  if (check.checked_at) return <Tag color="success">Hoạt động</Tag>;
  return <Tag>Chưa kiểm tra</Tag>;
}

/** One number of a Page, small: the value over its label. */
function Figure({ label, value, note }: { label: string; value: string; note?: React.ReactNode }) {
  return (
    <Flex vertical gap={0} style={{ minWidth: 0 }}>
      <Typography.Text strong style={{ fontSize: 15, lineHeight: "22px" }}>
        {value}
        {note}
      </Typography.Text>
      <Typography.Text type="secondary" style={{ fontSize: 12 }} ellipsis>
        {label}
      </Typography.Text>
    </Flex>
  );
}

/** "+12" after the followers, this week's gain; nothing until there is a number from last week. */
function Gain({ gain }: { gain: number | null }) {
  if (!gain) return null;
  return (
    <Typography.Text type={gain > 0 ? "success" : "secondary"} style={{ fontSize: 12, fontWeight: 400, marginLeft: 4 }}>
      {gain > 0 ? "+" : ""}
      {number(gain)}
    </Typography.Text>
  );
}

/** Whose Page it is and, for its owner, the Shopee account whose links its comments carry (one of their own). A Page
 * that belongs to nobody is taken with "Nhận Page này". */
function OwnerLine({
  row,
  accounts,
  onRows,
}: {
  row: Fanpage;
  accounts: AffiliateAccount[];
  onRows: (rows: Fanpage[]) => void;
}) {
  const { message } = App.useApp();

  async function call(path: string, method: "POST" | "PUT", body?: object) {
    try {
      onRows(await api<Fanpage[]>(path, method, body));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  if (!row.owner) {
    return (
      <Flex justify="space-between" align="center" gap={8} data-testid="fanpage-owner">
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Chưa thuộc ai
        </Typography.Text>
        <Button size="small" onClick={() => call(`/fanpages/${row.id}/owner`, "POST")}>
          Nhận Page này
        </Button>
      </Flex>
    );
  }
  if (!row.mine) {
    return (
      <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="fanpage-owner">
        Thuộc: {row.owner.name}
      </Typography.Text>
    );
  }
  const shopee = accounts.filter((account) => account.platform === "shopee" && account.active);
  return (
    <Flex vertical gap={6} data-testid="fanpage-owner">
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Thuộc: bạn
      </Typography.Text>
      <Select
        size="small"
        aria-label={`Tài khoản Shopee của ${row.name}`}
        placeholder="Chưa gắn tài khoản Shopee (dùng link dán tay)"
        allowClear
        value={row.shopee_account?.id ?? null}
        options={shopee.map((account) => ({ value: account.id, label: `Shopee: ${account.name}` }))}
        onChange={(accountId: number | undefined) =>
          call(`/fanpages/${row.id}/shopee-account`, "PUT", { account_id: accountId ?? null })
        }
        notFoundContent={
          <Typography.Text type="secondary">Thêm tài khoản ở Cấu hình › Tài khoản affiliate</Typography.Text>
        }
      />
      {row.shopee_account && !row.shopee_account.usable && (
        <Typography.Text type="warning" style={{ fontSize: 12 }}>
          Tài khoản Shopee thiếu App ID/Secret hoặc đang ngừng dùng: bình luận dùng link dán tay
        </Typography.Text>
      )}
    </Flex>
  );
}

/** A Page in use, compact: who it is, whether its token works, its numbers, and what a member can do with it. */
function PageCard({
  row,
  accounts,
  onRows,
  onDays,
  onToken,
}: {
  row: Fanpage;
  accounts: AffiliateAccount[];
  onRows: (rows: Fanpage[]) => void;
  onDays: (row: Fanpage) => void;
  onToken: (row: Fanpage) => void;
}) {
  const { message, modal } = App.useApp();
  const { check, insights } = row;
  const week = insights.last_7_days;

  async function call(path: string, method: "POST" | "PATCH", body?: object) {
    try {
      onRows(await api<Fanpage[]>(path, method, body));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  function stop() {
    modal.confirm({
      title: `Ngừng dùng ${row.name}?`,
      content:
        "Page sẽ không còn trong hộp thoại Đăng, không được kiểm tra hay đọc số liệu nữa. Dùng lại được bất cứ lúc nào.",
      okText: "Ngừng dùng",
      okButtonProps: { danger: true },
      cancelText: "Huỷ",
      onOk: () => call(`/fanpages/${row.id}`, "PATCH", { active: false }),
    });
  }

  return (
    <Card
      size="small"
      data-testid="fanpage-card"
      style={{ height: "100%", borderColor: check.error ? COLORS.primaryBorder : undefined }}
      styles={{ body: { display: "flex", flexDirection: "column", gap: 10, height: "100%" } }}
    >
      <Flex gap={10} align="center">
        <Avatar size={32} style={{ background: COLORS.primaryBg, color: COLORS.primary, flex: "none" }}>
          {row.name.trim().charAt(0).toUpperCase() || <FacebookOutlined />}
        </Avatar>
        <Flex vertical style={{ minWidth: 0, flex: 1 }}>
          <Typography.Link href={pageUrl(row)} target="_blank" rel="noreferrer" strong ellipsis>
            {row.name}
          </Typography.Link>
          <Typography.Text type="secondary" style={{ fontSize: 12 }} ellipsis>
            ID {row.page_id} · token …{row.token_tail}
          </Typography.Text>
        </Flex>
        <StatusTag row={row} />
        <Dropdown
          trigger={["click"]}
          menu={{
            items: [
              { key: "token", label: "Dán token mới", onClick: () => onToken(row) },
              { key: "stop", label: "Ngừng dùng", icon: <StopOutlined />, danger: true, onClick: stop },
            ],
          }}
        >
          <Button type="text" size="small" icon={<MoreOutlined />} aria-label={`Thao tác với ${row.name}`} />
        </Dropdown>
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
            {row.scheduled_posts > 0 && ` · ${row.scheduled_posts} bài hẹn giờ bị ảnh hưởng`}
          </Typography.Text>
          <Button size="small" onClick={() => onToken(row)}>
            Dán token mới
          </Button>
        </Flex>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 8 }}>
        <Figure label="Theo dõi" value={count(check.followers)} note={<Gain gain={check.followers_this_week} />} />
        <Figure label="Lượt xem" value={count(week.views)} />
        <Figure label="Tiếp cận" value={count(week.reach)} />
        <Figure label="Tương tác" value={count(week.engagements)} />
      </div>
      {insights.error && (
        <Typography.Text type="warning" style={{ fontSize: 12 }}>
          {insights.error}
        </Typography.Text>
      )}
      <OwnerLine row={row} accounts={accounts} onRows={onRows} />

      <Flex justify="space-between" align="center" gap={8} style={{ marginTop: "auto" }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }} ellipsis>
          Số liệu 7 ngày · {check.checked_at ? `kiểm tra ${formatDateTime(check.checked_at)}` : "chưa kiểm tra"}
          {row.scheduled_posts > 0 && !check.error && ` · ${row.scheduled_posts} bài hẹn giờ`}
        </Typography.Text>
        <Space size={0}>
          <Tooltip title="Số liệu 30 ngày">
            <Button
              size="small"
              type="text"
              icon={<BarChartOutlined />}
              aria-label="30 ngày"
              onClick={() => onDays(row)}
            />
          </Tooltip>
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

/** The Page's numbers day by day for the last 30 days. */
function DaysModal({ row, onClose }: { row: Fanpage | null; onClose: () => void }) {
  const [days, setDays] = useState<FanpageDay[] | null>(null);
  const id = row?.id;
  useEffect(() => {
    if (id === undefined) return;
    let live = true;
    api<FanpageDay[]>(`/fanpages/${id}/insights`).then(
      (found) => live && setDays(found),
      () => live && setDays([]),
    );
    return () => {
      live = false;
    };
  }, [id]);
  return (
    <Modal
      title={`Số liệu 30 ngày · ${row?.name ?? ""}`}
      open={row !== null}
      onCancel={onClose}
      afterClose={() => setDays(null)}
      footer={null}
      width={720}
    >
      <Table<FanpageDay>
        size="small"
        rowKey="day"
        loading={days === null}
        dataSource={days ? [...days].reverse() : []}
        pagination={false}
        scroll={{ x: "max-content", y: 420 }}
        locale={{ emptyText: "Chưa có số liệu: tool đọc Page Insights ở mỗi lần kiểm tra" }}
        columns={[
          { title: "Ngày", dataIndex: "day", render: (day: string) => day.split("-").reverse().join("/") },
          { title: "Lượt xem", dataIndex: "views", render: count },
          { title: "Tiếp cận", dataIndex: "reach", render: count },
          { title: "Tương tác", dataIndex: "engagements", render: count },
          { title: "Người theo dõi", dataIndex: "followers", render: count },
        ]}
      />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Ngày theo cách Facebook tính (giờ Thái Bình Dương), nên lệch giờ Việt Nam một chút.
      </Typography.Text>
    </Modal>
  );
}

/** Pages no longer used, folded away: "Dùng lại", or "Xóa" for one that never had a post. */
function StoppedPages({ rows, onRows }: { rows: Fanpage[]; onRows: (rows: Fanpage[]) => void }) {
  const { message } = App.useApp();
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
                      ID {row.page_id} · {row.posts ? `${row.posts} bài đăng` : "chưa đăng bài nào"} · ngừng{" "}
                      {formatDateTime(row.updated_at)}
                      {row.updated_by ? ` bởi ${row.updated_by}` : ""}
                    </Typography.Text>
                  </Flex>
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
                </Flex>
              ))}
            </Flex>
          ),
        },
      ]}
    />
  );
}

function TokenInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <Input.Password
      aria-label="Token"
      value={value}
      autoComplete="new-password"
      placeholder="Dán token vào đây"
      onChange={(event) => onChange(event.target.value)}
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

function TokenModal({
  row,
  onClose,
  onSaved,
}: {
  row: Fanpage | null;
  onClose: () => void;
  onSaved: (rows: Fanpage[]) => void;
}) {
  const { message } = App.useApp();
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      onSaved(await api<Fanpage[]>(`/fanpages/${row?.id}/token`, "PUT", { token }));
      onClose();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title={`Dán token mới cho ${row?.name ?? ""}`}
      open={row !== null}
      onClose={onClose}
      destroyOnHidden
      afterClose={() => setToken("")}
      okText="Lưu"
      cancelText="Huỷ"
      confirmLoading={busy}
      okButtonProps={{ disabled: !token.trim() }}
      onOk={save}
    >
      <TokenInput value={token} onChange={setToken} />
    </FormDrawer>
  );
}

export default function FanpagesPage() {
  const { message } = App.useApp();
  const [rows, setRows] = useState<Fanpage[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [replacing, setReplacing] = useState<Fanpage | null>(null);
  const [days, setDays] = useState<Fanpage | null>(null);
  const [accounts, setAccounts] = useState<AffiliateAccount[]>([]);

  useEffect(() => {
    // Without them a Page shows its owner but offers no account to choose.
    api<AffiliateAccount[]>("/affiliate-accounts").then(setAccounts, () => undefined);
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
  // Pages not checked lately are checked again on opening, without pressing "Kiểm tra ngay" on each.
  useFreshenOnOpen("/fanpages/freshen", load);

  // While a check waits for the worker, ask again every few seconds until it has answered.
  const pending = rows?.some((row) => row.active && row.check.pending) ?? false;
  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(() => void load(), 4000);
    return () => clearTimeout(timer);
  }, [pending, rows, load]);

  const inUse = (rows ?? []).filter((row) => row.active).sort(byNeed);
  const stopped = (rows ?? []).filter((row) => !row.active);
  const broken = inUse.filter((row) => row.check.error).length;

  return (
    <>
      <PageHeader
        title="Kết nối Fanpage"
        actions={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>
            Thêm Fanpage
          </Button>
        }
        description={
          <>
            Dán token của một System User trong Business Manager đã được gán Page, có quyền <code>pages_show_list</code>
            , <code>pages_read_engagement</code>, <code>pages_manage_posts</code>, <code>pages_manage_engagement</code>,{" "}
            <code>pages_read_user_content</code> và <code>read_insights</code>. Token được lưu mã hoá, không bao giờ
            hiện lại; tool tự kiểm tra lại mỗi 12 giờ.
          </>
        }
      />
      <Flex vertical gap={16}>
        {rows !== null && rows.length > 0 && (
          <Flex gap={8} wrap>
            <Tag color="success">{inUse.length} đang dùng</Tag>
            {broken > 0 && <Tag color="error">{broken} lỗi kết nối</Tag>}
            {stopped.length > 0 && <Tag>{stopped.length} ngừng dùng</Tag>}
          </Flex>
        )}
        {rows === null ? (
          <Card loading />
        ) : inUse.length === 0 ? (
          <Card>
            <Empty description={stopped.length ? "Không có Fanpage nào đang dùng" : "Chưa kết nối Fanpage nào"}>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setAdding(true)}>
                Thêm Fanpage
              </Button>
            </Empty>
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
                onRows={setRows}
                onDays={setDays}
                onToken={setReplacing}
              />
            ))}
          </div>
        )}
        <StoppedPages rows={stopped} onRows={setRows} />
      </Flex>
      <AddModal open={adding} onClose={() => setAdding(false)} onSaved={setRows} />
      <TokenModal row={replacing} onClose={() => setReplacing(null)} onSaved={setRows} />
      <DaysModal row={days} onClose={() => setDays(null)} />
    </>
  );
}
