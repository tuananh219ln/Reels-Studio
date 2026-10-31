import { redirect } from "next/navigation";

// "Cài đặt" is a menu group; its first page is the AI model settings.
export default function SettingsPage() {
  redirect("/settings/ai");
}
