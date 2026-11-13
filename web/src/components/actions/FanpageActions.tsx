"use client";
import FormDrawer from "@/components/FormDrawer";
import { useMe } from "@/components/MeContext";
import { api, errorMessage, upload, type AffiliateAccount, type BrandLogoResult, type Fanpage } from "@/lib/api";
import { DeleteOutlined, FacebookOutlined, MoreOutlined, StopOutlined } from "@ant-design/icons";
import { App, Button, Dropdown, Flex, Input, Popconfirm, Select, Spin, Switch, Typography } from "antd";
import { useEffect, useState } from "react";

export function OwnerLine({
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
  const tiktok = accounts.filter((account) => account.platform === "tiktok" && account.active);
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
          <Typography.Text type="secondary">Thêm tài khoản ở Cài đặt › Tài khoản affiliate</Typography.Text>
        }
      />
      {row.shopee_account && !row.shopee_account.usable && (
        <Typography.Text type="warning" style={{ fontSize: 12 }}>
          Tài khoản Shopee thiếu App ID/Secret hoặc đang ngừng dùng: bình luận dùng link dán tay
        </Typography.Text>
      )}
      <Select
        size="small"
        aria-label={`Tài khoản TikTok của ${row.name}`}
        placeholder="Chưa gắn tài khoản TikTok (chọn tay ở từng video)"
        allowClear
        value={row.tiktok_account?.id ?? null}
        options={tiktok.map((account) => ({
          value: account.id,
          label: `TikTok: ${account.name}${
            account.tiktok_connection?.username ? ` (@${account.tiktok_connection.username})` : ""
          }`,
        }))}
        onChange={(accountId: number | undefined) =>
          call(`/fanpages/${row.id}/tiktok-account`, "PUT", { account_id: accountId ?? null })
        }
        notFoundContent={
          <Typography.Text type="secondary">Kết nối TikTok ở Cài đặt › Tài khoản affiliate</Typography.Text>
        }
      />
      {row.tiktok_account && !row.tiktok_account.connected && (
        <Typography.Text type="warning" style={{ fontSize: 12 }}>
          Tài khoản TikTok chưa kết nối, hãy kết nối lại trong Cài đặt › Tài khoản affiliate
        </Typography.Text>
      )}
      <LogoLine row={row} onRows={onRows} />
    </Flex>
  );
}

/** The Page's logo ("Kênh"): laid on the MP4 of every video made for the Page, inside the platforms' safe zone. Its
 * owner uploads it or takes the Page's own picture; the brand is made on the first logo. */
function LogoLine({ row, onRows }: { row: Fanpage; onRows: (rows: Fanpage[]) => void }) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);
  const brand = row.brand;

  async function change(work: (brandId: number) => Promise<BrandLogoResult | null>) {
    setBusy(true);
    try {
      let brandId = brand?.id;
      if (brandId === undefined) {
        brandId = (await api<{ id: number }>("/brands", "POST", { name: row.name, fanpage_id: row.id })).id;
      }
      const result = await work(brandId);
      onRows(await api<Fanpage[]>("/fanpages"));
      if (result && result.videos_outdated > 0) {
        message.info(`${result.videos_outdated} video chưa đăng sẽ cần render lại để có logo mới`);
      }
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Flex vertical gap={6} data-testid="fanpage-logo">
      <Flex gap={8} align="center">
        {brand?.logo_badge_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- a small badge served by the api, no optimisation needed
          <img src={brand.logo_badge_url} alt={`Logo ${row.name}`} width={40} height={40} />
        ) : (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Chưa có logo (gắn vào video của Page này)
          </Typography.Text>
        )}
        <label>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            hidden
            aria-label={`Tải logo của ${row.name}`}
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void change((id) => upload<BrandLogoResult>(`/brands/${id}/logo`, file));
            }}
          />
          <Button
            size="small"
            loading={busy}
            onClick={(event) => event.currentTarget.parentElement?.querySelector("input")?.click()}
          >
            {brand?.logo_badge_url ? "Đổi logo" : "Tải logo"}
          </Button>
        </label>
        {row.picture && (
          <Button
            size="small"
            disabled={busy}
            onClick={() => change((id) => api<BrandLogoResult>(`/brands/${id}/logo/from-fanpage`, "POST"))}
          >
            Dùng ảnh Fanpage
          </Button>
        )}
        {brand?.logo_badge_url && (
          <Popconfirm
            title="Xoá logo của Page?"
            okText="Xoá"
            cancelText="Huỷ"
            onConfirm={() => change((id) => api<BrandLogoResult>(`/brands/${id}/logo`, "DELETE"))}
          >
            <Button size="small" danger type="text" icon={<DeleteOutlined />} aria-label="Xoá logo" />
          </Popconfirm>
        )}
      </Flex>
      {brand?.logo_badge_url && (
        <Flex gap={8} align="center">
          <Switch
            size="small"
            checked={brand.logo_default_on}
            disabled={busy}
            aria-label="Video mới của Page tự gắn logo"
            onChange={(on) =>
              change(async (id) => {
                await api(`/brands/${id}`, "PATCH", { logo_default_on: on });
                return null;
              })
            }
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Video của Page tự gắn logo
          </Typography.Text>
        </Flex>
      )}
    </Flex>
  );
}

export function TokenInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <Input.Password
      aria-label="Token"
      value={value}
      autoComplete="new-password"
      placeholder="Dán token vào đây…"
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

export function TokenModal({
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

export function FanpageMenu({
  row,
  onToken,
  onChanged,
  onSettings,
}: {
  row: Fanpage;
  onToken: () => void;
  onChanged: () => void | Promise<void>;
  onSettings?: () => void;
}) {
  const { me } = useMe();
  const { message, modal } = App.useApp();
  async function stop() {
    modal.confirm({
      title: `Ngừng dùng ${row.name}?`,
      content:
        "Page sẽ không còn trong hộp thoại Đăng, không được kiểm tra hay đọc số liệu nữa. Dùng lại được bất cứ lúc nào.",
      okText: "Ngừng dùng",
      cancelText: "Huỷ",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api(`/fanpages/${row.id}`, "PATCH", { active: false });
          await onChanged();
        } catch (err) {
          message.error(errorMessage(err));
          throw err;
        }
      },
    });
  }
  return (
    <Dropdown
      trigger={["click"]}
      menu={{
        items: [
          {
            key: "facebook",
            icon: <FacebookOutlined />,
            label: (
              <a href={`https://www.facebook.com/${row.page_id}`} target="_blank" rel="noreferrer">
                Mở trên Facebook
              </a>
            ),
          },
          { key: "token", label: "Dán token mới", onClick: onToken },
          ...(onSettings ? [{ key: "settings", label: "Tài khoản và chủ Page", onClick: onSettings }] : []),
          ...(row.active && row.owner?.id === me.id
            ? [{ key: "stop", icon: <StopOutlined />, label: "Ngừng dùng", danger: true, onClick: () => void stop() }]
            : []),
        ],
      }}
    >
      <Button type="text" size="small" icon={<MoreOutlined />} aria-label={`Thao tác với ${row.name}`} />
    </Dropdown>
  );
}

export default function FanpageActions({
  pageId,
  onChanged,
}: {
  pageId: number;
  onChanged: () => void | Promise<void>;
}) {
  const { message } = App.useApp();
  const [row, setRow] = useState<Fanpage | null>(null);
  const [accounts, setAccounts] = useState<AffiliateAccount[]>([]);
  const [settings, setSettings] = useState(false);
  const [token, setToken] = useState(false);
  useEffect(() => {
    let live = true;
    Promise.all([api<Fanpage[]>("/fanpages"), api<AffiliateAccount[]>("/affiliate-accounts")]).then(
      ([pages, found]) => {
        if (live) {
          setRow(pages.find((page) => page.id === pageId) ?? null);
          setAccounts(found);
        }
      },
      (err) => {
        if (live) message.error(errorMessage(err));
      },
    );
    return () => {
      live = false;
    };
  }, [pageId, message]);
  async function receive(rows: Fanpage[]) {
    setRow(rows.find((page) => page.id === pageId) ?? null);
    await onChanged();
  }
  async function refresh() {
    await receive(await api<Fanpage[]>("/fanpages"));
  }
  if (!row) return <Spin size="small" />;
  return (
    <>
      <FanpageMenu row={row} onToken={() => setToken(true)} onSettings={() => setSettings(true)} onChanged={refresh} />
      <TokenModal row={token ? row : null} onClose={() => setToken(false)} onSaved={(rows) => void receive(rows)} />
      <FormDrawer
        title={`Tài khoản và chủ Page ${row.name}`}
        open={settings}
        onClose={() => setSettings(false)}
        footer={null}
      >
        <OwnerLine row={row} accounts={accounts} onRows={(rows) => void receive(rows)} />
      </FormDrawer>
    </>
  );
}
