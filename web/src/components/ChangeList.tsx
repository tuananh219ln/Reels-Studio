"use client";

import { Flex, Typography } from "antd";
import Link from "next/link";
import { COLORS } from "@/app/theme";
import { formatDateTime } from "@/lib/api";
import { byDeploy, type ChangeEntry, KIND_LABEL, SCREENS } from "@/lib/changelog";

/** The changes of "Có gì mới", in the window and on its page: one group per deploy ("Cập nhật <time>"), newest first;
 * in each, the headline ("Mới" while unseen), the detail, then the kind and time, "Thử ngay" on the screens the
 * change touched and "Xem hướng dẫn" when its PR wrote an in-app guide. */
export default function ChangeList({
  entries,
  unseen,
  onLeave,
}: {
  entries: ChangeEntry[];
  unseen: Set<number>;
  /** The window closes when one of its links is followed. */
  onLeave?: () => void;
}) {
  return (
    <Flex vertical gap={24} data-testid="whats-new-list">
      {byDeploy(entries).map((group) => (
        <Flex vertical gap={16} key={group.deployed_at ?? "all"} data-testid="whats-new-deploy">
          {group.deployed_at && (
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              Cập nhật {formatDateTime(group.deployed_at)}
            </Typography.Text>
          )}
          {group.entries.map((entry) => (
            <div key={entry.number} data-testid="whats-new-entry">
              <Flex align="baseline" gap={8} wrap>
                <Typography.Text strong>{entry.title}</Typography.Text>
                {unseen.has(entry.number) && (
                  <Typography.Text style={{ color: COLORS.primary, fontSize: 12 }}>Mới</Typography.Text>
                )}
              </Flex>
              {entry.summary && (
                <Typography.Paragraph type="secondary" style={{ margin: "2px 0 0", maxWidth: 820 }}>
                  {entry.summary}
                </Typography.Paragraph>
              )}
              <Flex gap={12} wrap align="baseline">
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {KIND_LABEL[entry.kind]}, {formatDateTime(entry.merged_at)}
                </Typography.Text>
                {(entry.pages ?? []).map((path) => (
                  <Link key={path} href={path} onClick={onLeave} style={{ fontSize: 12 }}>
                    Thử ngay: {SCREENS[path.slice(1)] ?? path}
                  </Link>
                ))}
                {(entry.guides ?? []).map((slug, index, all) => (
                  <Link key={slug} href={`/guides?guide=${slug}`} onClick={onLeave} style={{ fontSize: 12 }}>
                    {all.length > 1 ? `Xem hướng dẫn ${index + 1}` : "Xem hướng dẫn"}
                  </Link>
                ))}
              </Flex>
            </div>
          ))}
        </Flex>
      ))}
    </Flex>
  );
}
