import { Avatar } from "antd";
import { TEAL } from "@/app/theme";

export default function UserAvatar({ initial, size = 32 }: { initial: string; size?: number }) {
  return (
    <Avatar size={size} style={{ background: "#E6F0F3", color: TEAL, fontWeight: 600, flexShrink: 0 }}>
      {initial}
    </Avatar>
  );
}
