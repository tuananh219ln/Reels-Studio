"use client";

import { Flex, Typography } from "antd";
import Link from "next/link";
import { COLORS } from "@/app/theme";
import { formatDateTime } from "@/lib/api";
import { type ChangeEntry, KIND_LABEL } from "@/lib/changelog";

/** The changes of "Có gì mới", newest first, in the window and on its page: the headline ("Mới" while unseen), the
 * detail, then the kind and time, and "Xem hướng dẫn" when the change's PR wrote an in-app guide. */
export default function ChangeList({
  entries,
  unseen,
  onOpenGuide,
}: {
  entries: ChangeEntry[];
  unseen: Set<number>;
  /** The window closes when a guide is opened from it. */
  onOpenGuide?: () => void;
}) {
  return (
    <Flex vertical gap={16} data-testid="whats-new-list">
      {entries.map((entry) => (
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
            {(entry.guides ?? []).map((slug, index, all) => (
              <Link key={slug} href={`/guides?guide=${slug}`} onClick={onOpenGuide} style={{ fontSize: 12 }}>
                {all.length > 1 ? `Xem hướng dẫn ${index + 1}` : "Xem hướng dẫn"}
              </Link>
            ))}
          </Flex>
        </div>
      ))}
    </Flex>
  );
}
