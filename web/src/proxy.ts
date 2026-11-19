import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "./lib/session";

// Optimistic check before any app page renders: without a session cookie there is nothing to show.
// The API still validates the session on every request.
export function proxy(request: NextRequest) {
  if (!request.cookies.has(SESSION_COOKIE)) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

// Every page except the public ones: the homepage `/` (a landing page for visitors, TikTok's app review included),
// the login screen and the privacy and terms pages. New pages are covered without touching this list: only `/` and
// /login, /privacy and /terms (exactly), the /api proxy, Next.js assets and files with an extension (favicon, images)
// are left out. `$` first in the group matches the empty path after the leading slash, that is `/` alone.
export const config = {
  matcher: ["/((?!$|login|privacy$|terms$|api/|_next/|.*\\..*).*)"],
};
