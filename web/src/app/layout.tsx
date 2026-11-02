import type { Metadata, Viewport } from "next";
import { AntdRegistry } from "@ant-design/nextjs-registry";
import { Be_Vietnam_Pro } from "next/font/google";
import Providers from "./providers";
import "./globals.css";

// Drawn for Vietnamese: its diacritics stack cleanly, unlike most system fonts. Served by the app itself.
const font = Be_Vietnam_Pro({
  subsets: ["vietnamese", "latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-app",
});

export const metadata: Metadata = {
  title: "Reels Studio",
  description: "Công cụ nội bộ làm video dọc 9:16",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className={font.variable}>
      <body>
        <AntdRegistry>
          <Providers>{children}</Providers>
        </AntdRegistry>
      </body>
    </html>
  );
}
