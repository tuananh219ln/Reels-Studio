import { Avatar } from "antd";
import { COLORS } from "@/app/theme";

export default function UserAvatar({ initial, size = 32 }: { initial: string; size?: number }) {
  return (
    <Avatar size={size} style={{ background: COLORS.primaryBg, color: COLORS.primary, fontWeight: 600, flexShrink: 0 }}>
      {initial}
    </Avatar>
  );
}
