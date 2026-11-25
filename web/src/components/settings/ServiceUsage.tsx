"use client";

import { formatCount } from "@/lib/format";
import { ReloadOutlined } from "@ant-design/icons";
import { Button, Flex, Progress, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, formatDateTime, formatDecimal } from "@/lib/api";

/** What /settings/sources/usage answers (service_usage.py). `ok: false` carries the reason in `error`. */
type Calls = { image: number; edit: number; voice: number };
type Checked = { ok?: boolean; error?: string };
export type ServiceUsage = {
  elevenlabs: Checked & {
    configured: boolean;
    usage_url: string;
    tier?: string;
    characters_used?: number;
    characters_limit?: number;
    resets_at?: string | null;
  };
  cloudflare: Checked & {
    configured: boolean;
    neurons_used?: number;
    neurons_limit: number;
    calls_today: Calls;
    resets_at: string;
    usage_url: string;
  };
  gemini: { configured: boolean; calls_today: Calls; resets_at: string; usage_url: string };
};

/** FLUX.1 schnell's 10,000 free neurons make about 57 photos: about 175 neurons each. */
const NEURONS_PER_PHOTO = 10_000 / 57;

const number = formatCount;

/** The usage lines, read apart from the page so the page shows at once while the services answer. */
export function useServiceUsage() {
  const [usage, setUsage] = useState<ServiceUsage | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async (fresh: boolean) => {
    setLoading(true);
    try {
      setUsage(await api<ServiceUsage>(`/settings/sources/usage${fresh ? "?fresh=true" : ""}`));
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void load(false);
  }, [load]);

  // `reload` after a key is saved: answers are kept per key, so a new key is asked at once.
  return { usage, loading, failed, refresh: () => load(true), reload: () => load(false) };
}

function Shell({
  testId,
  loading,
  onRefresh,
  children,
}: {
  testId: string;
  loading: boolean;
  onRefresh: () => void;
  children: React.ReactNode;
}) {
  return (
    <Flex vertical gap={4} data-testid={testId}>
      <Flex justify="space-between" align="center" gap={8}>
        <Typography.Text strong>Hạn mức</Typography.Text>
        <Button size="small" type="text" icon={<ReloadOutlined />} loading={loading} onClick={onRefresh}>
          Làm mới
        </Button>
      </Flex>
      {children}
    </Flex>
  );
}

function callsText(calls: Calls, kinds: (keyof Calls)[]): string {
  const names: Record<keyof Calls, string> = { image: "ảnh", edit: "lần sửa ảnh", voice: "lượt đọc lời" };
  return kinds.map((kind) => `${number(calls[kind])} ${names[kind]}`).join(", ");
}

type Props = { usage: ServiceUsage | null; loading: boolean; failed: boolean; onRefresh: () => void };

function Pending({ loading, failed }: { loading: boolean; failed: boolean }) {
  return (
    <Typography.Text type="secondary">
      {failed && !loading ? "Không đọc được hạn mức, bấm Làm mới để thử lại." : "Đang đọc hạn mức…"}
    </Typography.Text>
  );
}

export function ElevenLabsUsage({ usage, loading, failed, onRefresh }: Props) {
  const data = usage?.elevenlabs;
  if (usage && !data?.configured) return null;
  return (
    <Shell testId="usage-elevenlabs" loading={loading} onRefresh={onRefresh}>
      {!data ? (
        <Pending loading={loading} failed={failed} />
      ) : data.ok && data.characters_limit ? (
        <>
          <Progress
            percent={Math.min(100, ((data.characters_used ?? 0) / data.characters_limit) * 100)}
            showInfo={false}
            size="small"
          />
          <Typography.Text>
            Còn {number(Math.max(0, data.characters_limit - (data.characters_used ?? 0)))} ký tự (đã dùng{" "}
            {number(data.characters_used ?? 0)} / {number(data.characters_limit)}
            {data.tier ? `, gói ${data.tier}` : ""})
          </Typography.Text>
          {data.resets_at && (
            <Typography.Text type="secondary">Gói làm mới ký tự lúc {formatDateTime(data.resets_at)}.</Typography.Text>
          )}
        </>
      ) : (
        <Typography.Text type="warning">{data.error ?? "ElevenLabs không trả hạn mức."}</Typography.Text>
      )}
    </Shell>
  );
}

export function CloudflareUsage({ usage, loading, failed, onRefresh }: Props) {
  const data = usage?.cloudflare;
  if (usage && !data?.configured) return null;
  return (
    <Shell testId="usage-cloudflare" loading={loading} onRefresh={onRefresh}>
      {!data ? (
        <Pending loading={loading} failed={failed} />
      ) : (
        <>
          {data.ok && data.neurons_used !== undefined ? (
            <>
              <Progress
                percent={Math.min(100, (data.neurons_used / data.neurons_limit) * 100)}
                showInfo={false}
                size="small"
              />
              <Typography.Text>
                Còn khoảng{" "}
                {number(Math.max(0, Math.floor((data.neurons_limit - data.neurons_used) / NEURONS_PER_PHOTO)))} ảnh hôm
                nay (đã dùng {formatDecimal(data.neurons_used, 0)} / {number(data.neurons_limit)} neurons)
              </Typography.Text>
            </>
          ) : (
            <>
              <Typography.Text type="warning">{data.error}</Typography.Text>
              <Typography.Text>
                Hôm nay app đã gọi: {callsText(data.calls_today, ["image", "edit"])} (còn khoảng{" "}
                {number(Math.max(0, 57 - data.calls_today.image - data.calls_today.edit))} ảnh nếu tài khoản chỉ dùng
                cho app).
              </Typography.Text>
            </>
          )}
          <Typography.Text type="secondary">
            Gói miễn phí không hết hạn; lượt mở lại lúc {formatDateTime(data.resets_at)}.
          </Typography.Text>
        </>
      )}
    </Shell>
  );
}

export function GeminiUsage({ usage, loading, failed, onRefresh }: Props) {
  const data = usage?.gemini;
  if (usage && !data?.configured) return null;
  return (
    <Shell testId="usage-gemini" loading={loading} onRefresh={onRefresh}>
      {!data ? (
        <Pending loading={loading} failed={failed} />
      ) : (
        <>
          <Typography.Text>
            Hôm nay app đã gọi: {callsText(data.calls_today, ["image", "edit", "voice"])}.
          </Typography.Text>
          <Typography.Text type="secondary">
            Google không cho đọc hạn mức còn lại hay số tiền đã dùng qua API, nên đây là số app tự đếm; giới hạn theo
            ngày tính lại lúc {formatDateTime(data.resets_at)}.{" "}
            <Typography.Link href={data.usage_url} target="_blank" rel="noreferrer">
              Xem hạn mức trên AI Studio
            </Typography.Link>
          </Typography.Text>
        </>
      )}
    </Shell>
  );
}
