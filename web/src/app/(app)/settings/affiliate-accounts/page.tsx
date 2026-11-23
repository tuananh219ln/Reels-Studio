"use client";

import EmptyState from "@/components/EmptyState";
import FormDrawer from "@/components/FormDrawer";
import { useMe } from "@/components/MeContext";
import ConnectionRow from "@/components/settings/ConnectionRow";
import { SettingsHeader } from "@/components/settings/SettingsBlocks";
import StatusText from "@/components/StatusText";
import WhoseFilter, { type Whose } from "@/components/WhoseFilter";
import { api, errorMessage, formatDateTime, type AffiliateAccount, type Channels, type Fanpage } from "@/lib/api";
import { useUrlChoice } from "@/lib/urlState";
import { DeleteOutlined, DisconnectOutlined, DownOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Avatar,
  Button,
  Card,
  Dropdown,
  Flex,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Switch,
  Typography,
} from "antd";
import { Suspense, useCallback, useEffect, useState } from "react";

type Fields = { platform: "shopee" | "tiktok"; name: string; app_id?: string; secret?: string; profile_url?: string };
type YouTubeChannel = Channels["youtube"][number];

/** "Dùng cho Page: A, B" or "Chưa gắn cho Page nào": the Pages of the member that picked this connection. */
function usedBy(pages: Fanpage[], picked: (page: Fanpage) => boolean): string {
  const names = pages.filter(picked).map((page) => page.name);
  return names.length ? `Dùng cho Page: ${names.join(", ")}` : "Chưa gắn cho Page nào";
}

export default function ConnectionsPage() {
  // "Của tôi / Cả đội" is in the address, which a static page only knows in the browser.
  return (
    <Suspense fallback={null}>
      <Connections />
    </Suspense>
  );
}

/** "Tài khoản và kênh": every account and channel a member connects to post and earn, as one list of rows. "Của tôi"
 * is where they are added, connected again and removed (a Shopee Secret only ever goes in); "Cả đội" reads the TikTok
 * and YouTube channels the whole team has, without changing anyone else's. A Page picks among the member's own from
 * its "Cài đặt" on Quản lý kênh. */
function Connections() {
  const { message } = App.useApp();
  const { me } = useMe();
  const [whose, setWhose] = useUrlChoice<Whose>("whose", "mine", ["mine", "all"]);
  const [accounts, setAccounts] = useState<AffiliateAccount[]>([]);
  const [channels, setChannels] = useState<Channels | null>(null);
  const [pages, setPages] = useState<Fanpage[]>([]);
  const [loading, setLoading] = useState(true);
  const [target, setTarget] = useState<AffiliateAccount | "new" | null>(null);
  const [linking, setLinking] = useState(false);
  const [checking, setChecking] = useState<number | null>(null);
  const [connecting, setConnecting] = useState<"tiktok" | "youtube" | null>(null);

  const reload = useCallback(async () => {
    try {
      const [found, all, rows] = await Promise.all([
        api<AffiliateAccount[]>("/affiliate-accounts"),
        api<Channels>("/channels"),
        api<Fanpage[]>("/fanpages"),
      ]);
      setAccounts(found);
      setChannels(all);
      setPages(rows);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void reload();
  }, [reload]);

  // Back from TikTok's or Google's consent page: say how the connection went, once, then drop it from the address.
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    for (const [key, name] of [
      ["tiktok", "TikTok"],
      ["youtube", "YouTube"],
    ] as const) {
      const outcome = query.get(key);
      if (outcome === "connected") {
        message.success(`Đã kết nối ${key === "tiktok" ? "tài khoản TikTok" : "kênh YouTube"}`);
      } else if (outcome === "error") {
        message.error(query.get("message") || `Không kết nối được ${name}, hãy thử lại`);
      }
      if (outcome) {
        query.delete(key);
        query.delete("message");
        const rest = query.toString();
        window.history.replaceState(null, "", window.location.pathname + (rest ? `?${rest}` : ""));
      }
    }
  }, [message]);

  /** "Kết nối TikTok" / "Kết nối YouTube": the api gives the consent page, and the browser goes there itself; it
   * then sends it back here with ?tiktok= or ?youtube=connected|error. Not a link to the api: the /api proxy in
   * production follows redirects itself instead of handing them to the browser. */
  async function connect(platform: "tiktok" | "youtube") {
    setConnecting(platform);
    try {
      const { url } = await api<{ url: string }>(`/${platform}/oauth/start`);
      window.location.assign(url);
    } catch (err) {
      message.error(errorMessage(err));
      setConnecting(null);
    }
  }

  async function run(work: () => Promise<unknown>, done?: string) {
    try {
      await work();
      if (done) message.success(done);
      await reload();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  const disconnectTikTok = (account: AffiliateAccount) =>
    account.tiktok_connection
      ? run(() => api(`/tiktok/connections/${account.tiktok_connection!.id}`, "DELETE"), "Đã ngắt kết nối TikTok")
      : undefined;

  const save = (account: AffiliateAccount, changes: Partial<Fields> & { active?: boolean }) =>
    run(() =>
      api(`/affiliate-accounts/${account.id}`, "PUT", {
        platform: account.platform,
        name: account.name,
        app_id: account.app_id,
        profile_url: account.profile_url,
        active: account.active,
        ...changes,
      }),
    );

  async function check(account: AffiliateAccount) {
    setChecking(account.id);
    try {
      const result = await api<{ ok: boolean; error: string | null }>(
        `/affiliate-accounts/${account.id}/check`,
        "POST",
      );
      if (result.ok) {
        message.success("Shopee nhận App ID và Secret này");
      } else {
        message.error(result.error ?? "Shopee từ chối");
      }
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setChecking(null);
    }
  }

  const removeAccount = (account: AffiliateAccount) =>
    run(() => api(`/affiliate-accounts/${account.id}`, "DELETE"), "Đã xoá tài khoản");

  const mine = (channel: YouTubeChannel) => channel.connection?.owner_id === me.id || channel.created_by_id === me.id;
  const shopee = accounts.filter((account) => account.platform === "shopee");
  const tiktok = accounts.filter((account) => account.platform === "tiktok");
  const youtube = (channels?.youtube ?? []).filter(mine);

  function section(title: string, count: number, rows: React.ReactNode, empty: string) {
    return (
      <Card
        size="small"
        title={`${title} (${count})`}
        styles={{ body: { padding: 0 } }}
        loading={loading}
        data-testid={`connections-${title.toLowerCase()}`}
      >
        {count ? rows : <EmptyState description={empty} />}
      </Card>
    );
  }

  return (
    <Flex vertical gap={16}>
      <SettingsHeader
        title="Tài khoản và kênh"
        description="Mọi tài khoản bạn kết nối để đăng và kiếm tiền. Đây là nơi thêm, kết nối lại và xoá; mỗi Page chọn trong số này ở nút Cài đặt của nó trên Quản lý kênh."
        actions={
          <Dropdown
            trigger={["click"]}
            menu={{
              items: [
                { key: "tiktok", label: "Kết nối TikTok", onClick: () => void connect("tiktok") },
                { key: "youtube", label: "Kết nối YouTube", onClick: () => void connect("youtube") },
                { key: "account", label: "Thêm tài khoản", onClick: () => setTarget("new") },
                { key: "link", label: "Thêm kênh bằng link", onClick: () => setLinking(true) },
              ],
            }}
          >
            <Button type="primary" icon={<PlusOutlined />} loading={connecting !== null}>
              Thêm kết nối <DownOutlined />
            </Button>
          </Dropdown>
        }
      />
      <WhoseFilter value={whose} onChange={setWhose} />

      {whose === "mine" ? (
        <>
          {section(
            "Shopee",
            shopee.length,
            shopee.map((account) => (
              <ConnectionRow
                key={account.id}
                testId="connection-shopee"
                platform="Shopee"
                color="orange"
                title={account.name}
                lines={[
                  `App ID ${account.app_id}, Secret …${account.secret_tail}`,
                  usedBy(pages, (page) => page.shopee_account?.id === account.id),
                  ...(account.report_read_at ? [`Đọc đơn lần cuối ${formatDateTime(account.report_read_at)}`] : []),
                ]}
                status={
                  <StatusText tone={account.report_error ? "warning" : account.active ? "success" : "idle"}>
                    {account.report_error ?? (account.active ? "Đang dùng" : "Ngừng dùng")}
                  </StatusText>
                }
                actions={
                  <>
                    <Switch
                      aria-label={`Dùng ${account.name}`}
                      checked={account.active}
                      onChange={(active) => void save(account, { active })}
                    />
                    <Button loading={checking === account.id} onClick={() => void check(account)}>
                      Kiểm tra kết nối
                    </Button>
                    <AccountButtons account={account} onEdit={setTarget} onRemove={removeAccount} />
                  </>
                }
              />
            )),
            "Chưa có tài khoản Shopee nào",
          )}
          {section(
            "TikTok",
            tiktok.length,
            tiktok.map((account) => {
              const connection = account.tiktok_connection;
              return (
                <ConnectionRow
                  key={account.id}
                  testId="connection-tiktok"
                  platform="TikTok"
                  color="magenta"
                  title={account.name}
                  link={account.profile_url ? { href: account.profile_url, label: "Mở kênh ↗" } : undefined}
                  lines={[
                    account.profile_url ?? "",
                    usedBy(pages, (page) => page.tiktok_account?.id === account.id),
                    ...(account.report_error ? [account.report_error] : []),
                  ].filter(Boolean)}
                  status={<TikTokConnectionState account={account} />}
                  actions={
                    <>
                      <Switch
                        aria-label={`Dùng ${account.name}`}
                        checked={account.active}
                        onChange={(active) => void save(account, { active })}
                      />
                      {connection && !connection.needs_reconnect ? (
                        <Popconfirm
                          title="Ngắt kết nối TikTok?"
                          description="App sẽ không gửi video lên tài khoản này nữa. Bài đã đăng không bị đụng tới."
                          okText="Ngắt kết nối"
                          cancelText="Huỷ"
                          onConfirm={() => void disconnectTikTok(account)}
                        >
                          <Button icon={<DisconnectOutlined />}>Ngắt kết nối</Button>
                        </Popconfirm>
                      ) : (
                        <Button loading={connecting === "tiktok"} onClick={() => void connect("tiktok")}>
                          {connection ? "Kết nối lại" : "Kết nối TikTok"}
                        </Button>
                      )}
                      <AccountButtons account={account} onEdit={setTarget} onRemove={removeAccount} />
                    </>
                  }
                />
              );
            }),
            "Chưa có tài khoản TikTok nào",
          )}
          {section(
            "YouTube",
            youtube.length,
            youtube.map((channel) => (
              <ConnectionRow
                key={channel.id}
                testId="connection-youtube"
                platform="YouTube"
                color="red"
                title={channel.name}
                link={{ href: channel.url, label: "Mở kênh ↗" }}
                lines={[`${channel.post_count} bài`, usedBy(pages, (page) => page.youtube_channel?.id === channel.id)]}
                status={<YouTubeState channel={channel} />}
                actions={
                  <>
                    {channel.connection?.needs_reconnect && (
                      <Button loading={connecting === "youtube"} onClick={() => void connect("youtube")}>
                        Kết nối lại
                      </Button>
                    )}
                    {channel.connection?.owner_id === me.id && (
                      <Popconfirm
                        title={`Ngắt kết nối ${channel.name}?`}
                        description="App quên quyền tải lên; video và bài đã ghi vẫn còn."
                        okText="Ngắt"
                        cancelText="Không"
                        onConfirm={() =>
                          run(
                            () => api(`/youtube/connections/${channel.connection!.id}`, "DELETE"),
                            "Đã ngắt kết nối YouTube",
                          )
                        }
                      >
                        <Button>Ngắt kết nối</Button>
                      </Popconfirm>
                    )}
                    {channel.created_by_id === me.id && !channel.connection && (
                      <Popconfirm
                        title={`Xóa kênh ${channel.name}?`}
                        description="Bài đã ghi trên kênh vẫn còn, chỉ không còn tên kênh."
                        okText="Xóa"
                        cancelText="Không"
                        okButtonProps={{ danger: true }}
                        onConfirm={() => run(() => api(`/channels/youtube/${channel.id}`, "DELETE"))}
                      >
                        <Button danger>Xóa</Button>
                      </Popconfirm>
                    )}
                  </>
                }
              />
            )),
            "Chưa có kênh YouTube nào. Bấm Thêm kết nối rồi Kết nối YouTube",
          )}
        </>
      ) : (
        <>
          {section(
            "TikTok",
            channels?.tiktok.length ?? 0,
            (channels?.tiktok ?? []).map((account) => (
              <ConnectionRow
                key={account.id}
                testId="channel-tiktok"
                platform="TikTok"
                color="magenta"
                title={account.name}
                link={account.url ? { href: account.url, label: "Mở kênh ↗" } : undefined}
                lines={[`${account.owner ?? "—"}, ${account.post_count} bài`]}
                status={
                  <StatusText tone={account.expired ? "danger" : account.connected ? "success" : "idle"}>
                    {account.expired
                      ? "Token hết hạn"
                      : account.connected
                        ? account.reads_views
                          ? "Đã kết nối, tự cập nhật view"
                          : "Đã kết nối"
                        : "Chưa kết nối"}
                  </StatusText>
                }
              />
            )),
            "Chưa có kênh TikTok nào",
          )}
          {section(
            "YouTube",
            channels?.youtube.length ?? 0,
            (channels?.youtube ?? []).map((channel) => (
              <ConnectionRow
                key={channel.id}
                testId="channel-youtube"
                platform="YouTube"
                color="red"
                title={channel.name}
                link={{ href: channel.url, label: "Mở kênh ↗" }}
                lines={[`${channel.created_by}, ${channel.post_count} bài`]}
                status={<YouTubeState channel={channel} />}
              />
            )),
            "Chưa có kênh YouTube nào",
          )}
        </>
      )}

      <AccountModal
        target={target}
        onClose={() => setTarget(null)}
        onDone={async () => {
          message.success("Đã lưu");
          setTarget(null);
          await reload();
        }}
      />
      <LinkDrawer
        open={linking}
        onClose={() => setLinking(false)}
        onDone={async (name) => {
          message.success(`Đã thêm kênh ${name}`);
          setLinking(false);
          await reload();
        }}
      />
    </Flex>
  );
}

function AccountButtons({
  account,
  onEdit,
  onRemove,
}: {
  account: AffiliateAccount;
  onEdit: (account: AffiliateAccount) => void;
  onRemove: (account: AffiliateAccount) => void;
}) {
  return (
    <>
      <Button aria-label={`Sửa ${account.name}`} icon={<EditOutlined />} onClick={() => onEdit(account)} />
      <Popconfirm
        title="Xoá tài khoản này?"
        description="Tài khoản đã có bài đăng hoặc đơn hàng thì chỉ ngừng dùng được."
        okText="Xoá"
        cancelText="Huỷ"
        onConfirm={() => onRemove(account)}
      >
        <Button aria-label={`Xoá ${account.name}`} danger icon={<DeleteOutlined />} />
      </Popconfirm>
    </>
  );
}

function YouTubeState({ channel }: { channel: YouTubeChannel }) {
  const connection = channel.connection;
  return (
    <StatusText tone={connection?.needs_reconnect ? "danger" : connection ? "success" : "idle"}>
      {connection?.needs_reconnect
        ? "Cần kết nối lại"
        : connection
          ? `Đã kết nối (${channel.connected_by ?? "—"})`
          : "Chưa kết nối"}
    </StatusText>
  );
}

/** "Thêm kênh bằng link": a TikTok channel (it becomes the member's TikTok account) or a YouTube one, from its link. */
function LinkDrawer({
  open,
  onClose,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  onDone: (name: string) => Promise<void>;
}) {
  const { message } = App.useApp();
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    setBusy(true);
    try {
      const added = await api<{ name: string }>("/channels", "POST", { url: link });
      setLink("");
      await onDone(added.name);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title="Thêm kênh bằng link"
      open={open}
      onClose={onClose}
      destroyOnHidden
      okText="Thêm kênh"
      cancelText="Huỷ"
      confirmLoading={busy}
      okButtonProps={{ disabled: !link.trim() }}
      onOk={add}
    >
      <Flex vertical gap={8}>
        <Input
          aria-label="Link kênh TikTok hoặc YouTube"
          placeholder="https://www.tiktok.com/@ten-kenh hoặc https://www.youtube.com/@ten-kenh…"
          value={link}
          onChange={(event) => setLink(event.target.value)}
          onPressEnter={() => link.trim() && void add()}
        />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Kênh TikTok là tài khoản TikTok của người thêm; bấm Kết nối TikTok để đăng qua API. View YouTube tự cập nhật
          (cần khóa YouTube API), view TikTok ở bản sau.
        </Typography.Text>
      </Flex>
    </FormDrawer>
  );
}

/** A TikTok account's connection through TikTok's API: who it is, how long it lasts, and whether to connect again. */
function TikTokConnectionState({ account }: { account: AffiliateAccount }) {
  const connection = account.tiktok_connection;
  if (!connection) {
    return (
      <Typography.Text type="secondary" data-testid="tiktok-connection">
        Chưa kết nối TikTok: chỉ ghi được bài đăng tay
      </Typography.Text>
    );
  }
  if (connection.needs_reconnect) {
    return (
      <Alert
        type="warning"
        showIcon
        data-testid="tiktok-connection"
        title={`Kết nối TikTok @${connection.username} đã hết hạn, hãy bấm Kết nối lại`}
        description={connection.last_error ?? undefined}
      />
    );
  }
  return (
    <Space size={6} data-testid="tiktok-connection">
      <Avatar size="small" src={connection.avatar_url ?? undefined}>
        {connection.display_name.slice(0, 1)}
      </Avatar>
      <Typography.Text>
        Đã kết nối @{connection.username}, còn hạn tới {formatDateTime(connection.refresh_expires_at)}
      </Typography.Text>
    </Space>
  );
}

function AccountModal({
  target,
  onClose,
  onDone,
}: {
  target: AffiliateAccount | "new" | null;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm<Fields>();
  const [busy, setBusy] = useState(false);
  const platform = Form.useWatch("platform", form) ?? "shopee";
  const adding = target === "new";

  useEffect(() => {
    if (target === null) {
      return;
    }
    form.resetFields();
    form.setFieldsValue(
      target === "new"
        ? { platform: "shopee" }
        : {
            platform: target.platform,
            name: target.name,
            app_id: target.app_id ?? undefined,
            profile_url: target.profile_url ?? undefined,
          },
    );
  }, [form, target]);

  async function submit(fields: Fields) {
    if (target === null) {
      return;
    }
    setBusy(true);
    try {
      await (target === "new"
        ? api("/affiliate-accounts", "POST", fields)
        : api(`/affiliate-accounts/${target.id}`, "PUT", { ...fields, active: target.active }));
      await onDone();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title={adding ? "Thêm tài khoản affiliate" : "Sửa tài khoản affiliate"}
      open={target !== null}
      onClose={onClose}
      onOk={() => form.submit()}
      okText={adding ? "Thêm" : "Lưu"}
      cancelText="Huỷ"
      confirmLoading={busy}
      forceRender
    >
      <Form form={form} layout="vertical" requiredMark={false} onFinish={submit}>
        <Form.Item label="Nền tảng" name="platform">
          <Select
            aria-label="Nền tảng"
            disabled={!adding}
            options={[
              { value: "shopee", label: "Shopee" },
              { value: "tiktok", label: "TikTok" },
            ]}
          />
        </Form.Item>
        <Form.Item
          label="Tên tài khoản"
          name="name"
          rules={[{ required: true, whitespace: true, message: "Nhập tên để nhận ra tài khoản" }]}
        >
          <Input placeholder={platform === "shopee" ? "Shopee của An" : "TikTok Dưỡng Sinh"} />
        </Form.Item>
        {platform === "shopee" ? (
          <>
            <Form.Item
              label="App ID"
              name="app_id"
              rules={[{ required: true, whitespace: true, message: "Nhập App ID" }]}
            >
              <Input autoComplete="off" />
            </Form.Item>
            <Form.Item
              label="Secret"
              name="secret"
              rules={[{ required: adding, whitespace: true, message: "Nhập Secret" }]}
              extra={adding ? undefined : "Để trống để giữ Secret đã lưu."}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
          </>
        ) : (
          <Form.Item
            label="Link kênh TikTok"
            name="profile_url"
            rules={[{ required: true, whitespace: true, message: "Dán link kênh TikTok" }]}
          >
            <Input placeholder="https://www.tiktok.com/@ten-kenh" />
          </Form.Item>
        )}
      </Form>
    </FormDrawer>
  );
}
