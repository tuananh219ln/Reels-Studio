import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_COOKIE } from "@/lib/session";
import Landing from "./Landing";

export const metadata: Metadata = {
  title: "Reels Studio",
  description:
    "Reels Studio is a web app that helps creators make short vertical videos (9:16) and publish them to TikTok.",
};

/** Public, with no session: the proxy leaves `/` open (proxy.ts). A signed-in member goes straight to the tool; the
 * cookie only picks the page to show, the API still checks the session on every request. */
export default async function Home() {
  if ((await cookies()).has(SESSION_COOKIE)) redirect("/videos");
  return <Landing />;
}
