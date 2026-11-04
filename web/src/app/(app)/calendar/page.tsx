import { redirect } from "next/navigation";

/** The calendar is now a view of "Bài đăng"; an old link or bookmark lands there. */
export default function CalendarPage() {
  redirect("/posts?view=calendar");
}
