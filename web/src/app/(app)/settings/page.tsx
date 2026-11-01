import { redirect } from "next/navigation";

// "Cấu hình" (in the Cài đặt menu group) opens on its first tab, the video defaults.
export default function SettingsPage() {
  redirect("/settings/defaults");
}
