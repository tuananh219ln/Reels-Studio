import { redirect } from "next/navigation";

/** Nguồn tư liệu is now part of "AI và nguồn tư liệu"; an old link or bookmark lands there. */
export default function SourcesPage() {
  redirect("/settings/ai");
}
