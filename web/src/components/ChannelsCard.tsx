"use client";

import { useMe } from "@/components/MeContext";
import StatusText from "@/components/StatusText";
import { api, errorMessage, formatDateTime, type Channels } from "@/lib/api";
import { PlusOutlined, YoutubeOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Input, List, Popconfirm, Switch, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

/** "Quản lý kênh"'s TikTok and YouTube channels, added from their link: posts made by hand there are recorded on
 * them ("Dán link bài đã đăng" on Bài đăng). A TikTok channel is the member's TikTok account, connected in Cài đặt;
 * a YouTube channel is connected here ("Kết nối YouTube"), and its member then uploads videos to it private. */
export default function ChannelsCard() {
  const { message } = App.useApp();
  const { me } = useMe();
  const [channels, setChannels] = useState<Channels | null>(null);
  const [link, setLink] = useState("");
  const [adding, setAdding] = useState(false);
  const [connecting, setConnecting] = useState(false);

  const load = useCallback(
    () =>
      api<Channels>("/channels").then(setChannels, (err) => {
        message.error(errorMessage(err));
      }),
    [message],
  );
  useEffect(() => {
    load();
  }, [load]);

  // Back from Google's consent page: say how the connection went, once, then drop it from the address.
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const outcome = query.get("youtube");
    if (outcome === "connected") {
      message.success("Đã kết nối kênh YouTube");
    } else if (outcome === "error") {
      message.error(query.get("message") || "Không kết nối được YouTube, hãy thử lại");
    }
    if (outcome) {
      query.delete("youtube");
      query.delete("message");
      const rest = query.toString();
      window.history.replaceState(null, "", window.location.pathname + (rest ? `?${rest}` : ""));
    }
  }, [message]);

  /** "Kết nối YouTube": the api gives Google's consent page and the browser goes there itself; Google sends it back
   * here with ?youtube=connected|error. Not a link to the api: the /api proxy follows redirects itself. */
  async function connectYouTube() {
    setConnecting(true);
    try {
      const { url } = await api<{ url: string }>("/youtube/oauth/start");
      window.location.assign(url);
    } catch (err) {
      message.error(errorMessage(err));
      setConnecting(false);
    }
  }

  async function disconnect(connectionId: number) {
    try {
      await api(`/youtube/connections/${connectionId}`, "DELETE");
      message.success("Đã ngắt kết nối YouTube");
      await load();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  async function add() {
    setAdding(true);
    try {
      const added = await api<{ name: string }>("/channels", "POST", { url: link });
      message.success(`Đã thêm kênh ${added.name}`);
      setLink("");
      await load();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setAdding(false);
    }
  }

  async function call(path: string, method: "PUT" | "POST", body: unknown, done: string) {
    try {
      await api(path, method, body);
      message.success(done);
      await load();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  async function remove(id: number) {
    try {
      await api(`/channels/youtube/${id}`, "DELETE");
      await load();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  return (
    <Card title="Kênh TikTok, YouTube và đồng bộ Facebook" data-testid="channels-card">
      <Flex vertical gap={16}>
        <Flex gap={8} wrap>
          <Input
            aria-label="Link kênh TikTok hoặc YouTube"
            placeholder="https://www.tiktok.com/@ten-kenh hoặc https://www.youtube.com/@ten-kenh"
            value={link}
            onChange={(event) => setLink(event.target.value)}
            onPressEnter={() => link.trim() && add()}
            style={{ flex: "1 1 320px" }}
          />
          <Button icon={<PlusOutlined />} loading={adding} disabled={!link.trim()} onClick={add}>
            Thêm kênh
          </Button>
        </Flex>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Kênh TikTok là tài khoản TikTok của người thêm; kết nối TikTok trong Cài đặt để đăng qua API. View YouTube tự
          cập nhật (cần khóa YouTube API), view TikTok ở bản sau. Reel đăng trên Page ngoài app được đồng bộ mỗi giờ.
        </Typography.Text>
        <div>
          <Typography.Title level={5}>Facebook: bài đăng ngoài app</Typography.Title>
          <List
            size="small"
            loading={channels === null}
            dataSource={channels?.facebook ?? []}
            locale={{ emptyText: "Chưa có Fanpage nào" }}
            renderItem={(page) => (
              <List.Item
                data-testid="channel-facebook"
                actions={[
                  <Button
                    key="now"
                    size="small"
                    loading={page.sync_pending}
                    onClick={() =>
                      call(`/channels/fanpage/${page.id}/sync-now`, "POST", {}, "Sẽ đồng bộ trong ít phút")
                    }
                  >
                    Đồng bộ ngay
                  </Button>,
                ]}
              >
                <Flex gap={12} align="center" wrap>
                  <Typography.Text strong>{page.name}</Typography.Text>
                  <Switch
                    size="small"
                    aria-label={`Đồng bộ bài ngoài app của ${page.name}`}
                    checked={page.sync_external_posts}
                    disabled={page.owner_id !== me.id}
                    onChange={(enabled) =>
                      call(
                        `/channels/fanpage/${page.id}/sync`,
                        "PUT",
                        { enabled },
                        enabled ? "Đã bật đồng bộ" : "Đã tắt đồng bộ",
                      )
                    }
                  />
                  <Typography.Text type="secondary">
                    {page.last_synced_at ? `Lần đồng bộ cuối ${formatDateTime(page.last_synced_at)}` : "Chưa đồng bộ"}
                  </Typography.Text>
                  {page.sync_error && <StatusText tone="danger">{page.sync_error}</StatusText>}
                </Flex>
              </List.Item>
            )}
          />
        </div>
        <div>
          <Typography.Title level={5}>TikTok</Typography.Title>
          <List
            size="small"
            loading={channels === null}
            dataSource={channels?.tiktok ?? []}
            locale={{ emptyText: "Chưa có kênh TikTok" }}
            renderItem={(account) => (
              <List.Item data-testid="channel-tiktok">
                <Flex gap={12} align="center" wrap style={{ width: "100%" }}>
                  <Typography.Text strong>{account.name}</Typography.Text>
                  {account.url && (
                    <a href={account.url} target="_blank" rel="noreferrer">
                      Mở kênh ↗
                    </a>
                  )}
                  <StatusText tone={account.expired ? "danger" : account.connected ? "success" : "idle"}>
                    {account.expired
                      ? "Token hết hạn"
                      : account.connected
                        ? account.reads_views
                          ? "Đã kết nối, tự cập nhật view"
                          : "Đã kết nối"
                        : "Chưa kết nối"}
                  </StatusText>
                  <Typography.Text type="secondary">
                    {account.owner ?? "—"} · {account.post_count} bài
                  </Typography.Text>
                </Flex>
              </List.Item>
            )}
          />
        </div>
        <div>
          <Flex justify="space-between" align="center" gap={8} wrap>
            <Typography.Title level={5} style={{ margin: 0 }}>
              YouTube
            </Typography.Title>
            <Button size="small" icon={<YoutubeOutlined />} loading={connecting} onClick={connectYouTube}>
              Kết nối YouTube
            </Button>
          </Flex>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Kênh đã kết nối nhận video tải lên ở chế độ riêng tư; bạn tự công khai hoặc hẹn giờ trong YouTube Studio.
          </Typography.Text>
          <List
            size="small"
            loading={channels === null}
            dataSource={channels?.youtube ?? []}
            locale={{ emptyText: "Chưa có kênh YouTube" }}
            renderItem={(channel) => (
              <List.Item
                data-testid="channel-youtube"
                actions={[
                  ...(channel.connection?.owner_id === me.id
                    ? [
                        <Popconfirm
                          key="disconnect"
                          title={`Ngắt kết nối ${channel.name}?`}
                          description="App quên quyền tải lên; video và bài đã ghi vẫn còn."
                          okText="Ngắt"
                          cancelText="Không"
                          onConfirm={() => channel.connection && disconnect(channel.connection.id)}
                        >
                          <Button size="small">Ngắt kết nối</Button>
                        </Popconfirm>,
                      ]
                    : []),
                  ...(channel.created_by_id === me.id && !channel.connection
                    ? [
                        <Popconfirm
                          key="delete"
                          title={`Xóa kênh ${channel.name}?`}
                          description="Bài đã ghi trên kênh vẫn còn, chỉ không còn tên kênh."
                          okText="Xóa"
                          cancelText="Không"
                          okButtonProps={{ danger: true }}
                          onConfirm={() => remove(channel.id)}
                        >
                          <Button size="small" danger>
                            Xóa
                          </Button>
                        </Popconfirm>,
                      ]
                    : []),
                ]}
              >
                <Flex gap={12} align="center" wrap>
                  <Typography.Text strong>{channel.name}</Typography.Text>
                  <a href={channel.url} target="_blank" rel="noreferrer">
                    Mở kênh ↗
                  </a>
                  <StatusText
                    tone={channel.connection?.needs_reconnect ? "danger" : channel.connection ? "success" : "idle"}
                  >
                    {channel.connection?.needs_reconnect
                      ? "Cần kết nối lại"
                      : channel.connection
                        ? `Đã kết nối (${channel.connected_by ?? "—"})`
                        : "Chưa kết nối"}
                  </StatusText>
                  <Typography.Text type="secondary">
                    {channel.created_by} · {channel.post_count} bài
                  </Typography.Text>
                </Flex>
              </List.Item>
            )}
          />
        </div>
      </Flex>
    </Card>
  );
}
