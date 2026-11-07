import type { Metadata } from "next";
import TermsOfService from "./TermsOfService";

export const metadata: Metadata = {
  title: "Điều khoản sử dụng — Reels Studio",
  description: "Điều khoản sử dụng của Reels Studio, công cụ nội bộ làm video dọc 9:16.",
};

/** Public, with no session: the proxy leaves /terms open (proxy.ts). */
export default function TermsPage() {
  return <TermsOfService />;
}
