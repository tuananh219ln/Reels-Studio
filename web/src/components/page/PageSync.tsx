"use client";

import { useMe } from "@/components/MeContext";
import StatusText from "@/components/StatusText";
import { api, errorMessage, formatDateTime, type Channels, type Fanpage } from "@/lib/api";
import { App, Button, Flex, Switch, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

/** "Đồng bộ bài đăng ngoài app" of one Page: reels posted on Facebook outside the app are imported hourly. Its owner
 * turns it on or off and can ask for a sync now; the others read when it last ran. */
export default function PageSync({ row }: { row: Fanpage }) {
  const { message } = App.useApp();
  const { me } = useMe();
  const [page, setPage] = useState<Channels["facebook"][number] | null | undefined>(undefined);

  const load = useCallback(
    () =>
      api<Channels>("/channels").then(
        (channels) => setPage(channels.facebook.find((one) => one.id === row.id) ?? null),
        (err) => message.error(errorMessage(err)),
      ),
    [message, row.id],
  );
  useEffect(() => {
    void load();
  }, [load]);

  async function call(path: string, method: "PUT" | "POST", body: unknown, done: string) {
    try {
      await api(path, method, body);
      message.success(done);
      await load();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  if (!page) return null;
  const owner = page.owner_id === me.id;
  return (
    <Flex vertical gap={6} data-testid="page-sync">
      <Flex gap={8} align="center">
        <Switch
          size="small"
          aria-label={`Đồng bộ bài ngoài app của ${row.name}`}
          checked={page.sync_external_posts}
          disabled={!owner}
          onChange={(enabled) =>
            call(`/channels/fanpage/${page.id}/sync`, "PUT", { enabled }, enabled ? "Đã bật đồng bộ" : "Đã tắt đồng bộ")
          }
        />
        <Typography.Text>Đồng bộ bài đăng ngoài app</Typography.Text>
      </Flex>
      <Flex gap={8} align="center" wrap>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {page.last_synced_at ? `Lần đồng bộ cuối ${formatDateTime(page.last_synced_at)}` : "Chưa đồng bộ"}
        </Typography.Text>
        {page.sync_error && <StatusText tone="danger">{page.sync_error}</StatusText>}
        {owner && (
          <Button
            size="small"
            loading={page.sync_pending}
            onClick={() => call(`/channels/fanpage/${page.id}/sync-now`, "POST", {}, "Sẽ đồng bộ trong ít phút")}
          >
            Đồng bộ ngay
          </Button>
        )}
      </Flex>
    </Flex>
  );
}
