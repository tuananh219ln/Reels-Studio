import type { Metadata } from "next";
import PrivacyPolicy from "./PrivacyPolicy";

export const metadata: Metadata = {
  title: "Chính sách quyền riêng tư — Reels Studio",
  description: "Chính sách quyền riêng tư của Reels Studio, công cụ nội bộ làm video dọc 9:16.",
};

/** Public, with no session: the proxy leaves /privacy open (proxy.ts). */
export default function PrivacyPage() {
  return <PrivacyPolicy />;
}
