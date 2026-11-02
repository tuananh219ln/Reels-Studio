import { COLORS } from "@/app/theme";

/** The app's icon (the browser tab's too, from src/app/icon.svg) beside its name: the brand's orange comes from it. */
export default function Logo({ size = 17 }: { size?: number }) {
  const icon = Math.round(size * 1.6);
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
      {/* By its address, not imported: the type for an .svg import only exists once Next has generated
          next-env.d.ts, which CI's typecheck runs before. /icon.svg is public (proxy.ts leaves files out). */}
      {/* eslint-disable-next-line @next/next/no-img-element -- a small static SVG, next/image adds nothing */}
      <img src="/icon.svg" alt="" width={icon} height={icon} style={{ borderRadius: icon * 0.24 }} />
      <span style={{ fontSize: size, fontWeight: 600, color: COLORS.text }}>Reels Studio</span>
    </span>
  );
}
