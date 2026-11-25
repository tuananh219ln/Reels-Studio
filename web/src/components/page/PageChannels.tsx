"use client";

import { PageSettingsDrawer } from "@/components/actions/FanpageActions";
import StatusText, { type StatusTone } from "@/components/StatusText";
import { api, type AffiliateAccount, type Fanpage, type YouTubeConnection } from "@/lib/api";
import { SettingOutlined } from "@ant-design/icons";
import { Button, Flex, Typography } from "antd";
import Link from "next/link";
import { useState } from "react";

/** The card's line on the Page's "Bộ bình luận" (api aff_sets.summaries). */
function affSetsLine(aff: Fanpage["aff_sets"]): string {
  if (aff.sets === 0) return "Chưa có bộ bình luận aff";
  if (!aff.enabled) return `Bộ bình luận aff: đang tắt (${aff.sets} bộ)`;
  return `Bộ bình luận aff: ${aff.usable}/${aff.sets} bộ dùng được, ${aff.per_post} bộ mỗi reel`;
}

type Line = { key: string; tone: StatusTone; text: string; testId?: string };

/** One read-only line per platform of a Page: what it is linked to and whether it posts there by itself. A status is
 * a dot and a words, never a control: changing it is "Cài đặt" (the drawer), so a card stays the same height
 * whatever is linked. The accounts only their owner may see (Shopee, TikTok, YouTube) are left out for the others. */
export function channelLines(row: Fanpage): Line[] {
  const lines: Line[] = [];
  if (row.mine) {
    lines.push(
      row.shopee_account
        ? {
            key: "shopee",
            tone: row.shopee_account.usable ? "success" : "warning",
            text: `Shopee: ${row.shopee_account.name}${row.shopee_account.usable ? "" : ", thiếu App ID/Secret hoặc đang ngừng dùng"}`,
          }
        : { key: "shopee", tone: "idle", text: "Shopee: dùng link dán tay" },
    );
    lines.push(
      row.tiktok_account
        ? {
            key: "tiktok",
            tone: row.tiktok_account.connected ? "success" : "warning",
            text: row.tiktok_account.connected
              ? `TikTok: ${row.tiktok_account.name}, ${row.tiktok_auto_mode === "direct" ? "đăng thẳng công khai" : "đẩy nháp đúng giờ"}`
              : `TikTok: ${row.tiktok_account.name}, mất kết nối`,
          }
        : { key: "tiktok", tone: "idle", text: "TikTok: chọn tay ở từng video" },
    );
  }
  lines.push(
    row.instagram
      ? {
          key: "instagram",
          tone: row.instagram_error ? "warning" : "success",
          text: `Instagram: @${row.instagram.username ?? row.instagram.id}, ${row.instagram_auto ? "tự đăng" : "chưa bật tự đăng"}`,
          testId: "fanpage-instagram",
        }
      : { key: "instagram", tone: "idle", text: "Chưa liên kết Instagram", testId: "fanpage-instagram" },
  );
  if (row.mine) {
    lines.push(
      row.youtube_channel
        ? {
            key: "youtube",
            tone: row.youtube_channel.connected ? "success" : "warning",
            text: row.youtube_channel.connected
              ? `YouTube: ${row.youtube_channel.name}, ${row.youtube_auto ? "tự đăng" : "chưa bật tự đăng"}`
              : `YouTube: ${row.youtube_channel.name}, mất kết nối`,
          }
        : { key: "youtube", tone: "idle", text: "YouTube: chọn tay ở từng video" },
    );
    lines.push({
      key: "logo",
      tone: row.brand?.logo_badge_url ? "success" : "idle",
      text: row.brand?.logo_badge_url
        ? `Logo: đã có${row.brand.logo_default_on ? ", video tự gắn" : ""}`
        : "Logo: chưa có",
    });
  }
  return lines;
}

/** Whose Page it is and what it posts to, as short lines (see channelLines), with "Cài đặt" for its owner and
 * "Nhận Page này" for a Page that belongs to nobody. Everything is changed in PageSettingsDrawer. */
export default function PageChannels({
  row,
  accounts,
  youtube,
  onRows,
}: {
  row: Fanpage;
  accounts: AffiliateAccount[];
  youtube: YouTubeConnection[];
  onRows: (rows: Fanpage[]) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Flex vertical gap={6} data-testid="fanpage-owner">
      <Flex justify="space-between" align="center" gap={8}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {row.owner ? `Thuộc: ${row.mine ? "bạn" : row.owner.name}` : "Chưa thuộc ai"}
        </Typography.Text>
        {!row.owner && (
          <Button size="small" onClick={async () => onRows(await api<Fanpage[]>(`/fanpages/${row.id}/owner`, "POST"))}>
            Nhận Page này
          </Button>
        )}
        {row.mine && (
          <Button
            size="small"
            icon={<SettingOutlined />}
            aria-label={`Cài đặt ${row.name}`}
            onClick={() => setOpen(true)}
          >
            Cài đặt
          </Button>
        )}
      </Flex>
      <Flex vertical gap={2}>
        {channelLines(row).map((line) => (
          <Typography.Text key={line.key} type="secondary" style={{ fontSize: 12 }} data-testid={line.testId}>
            <StatusText tone={line.tone}>{line.text}</StatusText>
          </Typography.Text>
        ))}
        {row.instagram_error && (
          // Why the last check could not read the account: the whole text, never cut, so the cause is readable.
          <Typography.Text type="warning" style={{ fontSize: 12 }} data-testid="fanpage-instagram-error">
            {row.instagram_error}
          </Typography.Text>
        )}
        <Typography.Text type="secondary" style={{ fontSize: 12 }} ellipsis data-testid="fanpage-aff-sets">
          <Link prefetch={false} href={`/affiliate?tab=sets&page=${row.id}`}>
            {affSetsLine(row.aff_sets)}
          </Link>
        </Typography.Text>
      </Flex>
      {row.mine && (
        <PageSettingsDrawer
          row={row}
          accounts={accounts}
          youtube={youtube}
          open={open}
          onClose={() => setOpen(false)}
          onRows={onRows}
        />
      )}
    </Flex>
  );
}
