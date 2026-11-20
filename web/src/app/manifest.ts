import type { MetadataRoute } from "next";
import { COLORS } from "./theme";

// Makes the app installable ("Cài app") on a phone's home screen or a computer. No service worker: the app is a
// live tool behind a login, so nothing is cached for offline use (decisions 2026-11-20).
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Reels Studio",
    short_name: "Reels Studio",
    description: "Công cụ nội bộ làm video dọc 9:16",
    lang: "vi",
    start_url: "/videos",
    scope: "/",
    display: "standalone",
    orientation: "any",
    background_color: COLORS.layout,
    theme_color: COLORS.brand,
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
