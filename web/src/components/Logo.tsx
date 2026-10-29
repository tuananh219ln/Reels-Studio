import { LOGO_GREEN } from "@/app/theme";

export default function Logo({ size = 17 }: { size?: number }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <span
        style={{
          background: LOGO_GREEN,
          color: "#12300A",
          fontWeight: 700,
          fontSize: size - 3,
          padding: "3px 7px",
          borderRadius: 6,
          lineHeight: 1.2,
        }}
      >
        RS
      </span>
      <span style={{ fontSize: size, fontWeight: 600, color: "#1F1F1F" }}>Reels Studio</span>
    </span>
  );
}
