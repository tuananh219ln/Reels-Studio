import { redirect } from "next/navigation";

// "Cài đặt" is a menu group; its first page is the video defaults.
export default function SettingsPage() {
  redirect("/settings/defaults");
}
