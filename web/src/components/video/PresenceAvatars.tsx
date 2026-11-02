"use client";

import { Avatar, Flex, Tooltip, Typography } from "antd";
import UserAvatar from "@/components/UserAvatar";
import type { PresentMember } from "@/lib/presence";

// The same blue as the outline round the scenes in "Chỉnh sửa".
const EDITING_BLUE = "#1677ff";

/** "Đang ở đây": the other members with this video open; whoever is editing has a blue ring. */
export default function PresenceAvatars({ others }: { others: PresentMember[] }) {
  if (others.length === 0) {
    return null;
  }
  return (
    <Flex align="center" gap={8} style={{ marginTop: 6 }} data-testid="presence">
      <Typography.Text type="secondary">Đang ở đây:</Typography.Text>
      <Avatar.Group max={{ count: 5 }} size={28}>
        {others.map((member) => {
          const doing = member.editing ? "đang chỉnh sửa" : "đang xem";
          return (
            <Tooltip key={member.id} title={`${member.name} · ${doing}`}>
              <span
                aria-label={`${member.name} ${doing}`}
                data-testid="presence-member"
                data-editing={member.editing}
                style={{
                  display: "inline-flex",
                  borderRadius: "50%",
                  boxShadow: member.editing ? `0 0 0 2px ${EDITING_BLUE}` : undefined,
                }}
              >
                <UserAvatar initial={member.initial} size={28} />
              </span>
            </Tooltip>
          );
        })}
      </Avatar.Group>
    </Flex>
  );
}

/** "Bình" / "Bình và An" / "Bình, An và Cường": the names of the members editing, for the warning. */
export function editorNames(others: PresentMember[]): string {
  const names = others.filter((member) => member.editing).map((member) => member.name.split(/\s+/).at(-1) ?? "");
  return names.length <= 1 ? (names[0] ?? "") : `${names.slice(0, -1).join(", ")} và ${names.at(-1)}`;
}
