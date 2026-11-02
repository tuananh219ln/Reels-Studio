import Image from "next/image";
import appIcon from "@/app/icon.svg";
import { COLORS } from "@/app/theme";

/** The app's icon (the browser tab's too) beside its name: the brand's orange comes from it. */
export default function Logo({ size = 17 }: { size?: number }) {
  const icon = Math.round(size * 1.6);
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
      <Image
        src={appIcon}
        alt=""
        width={icon}
        height={icon}
        style={{ borderRadius: icon * 0.24 }}
        unoptimized
        priority
      />
      <span style={{ fontSize: size, fontWeight: 600, color: COLORS.text }}>Reels Studio</span>
    </span>
  );
}
