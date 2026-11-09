import { redirect } from "next/navigation";

// "Cài đặt" opens on its first tab, the video defaults.
export default function SettingsPage() {
  redirect("/settings/defaults");
}
